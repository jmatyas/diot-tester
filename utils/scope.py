from artiq_tektronix_osc.driver import Tektronix4SeriesScope
import time

ip = "192.168.95.175"

class Scope(Tektronix4SeriesScope):
    def __init__(self, ip_address: str):
        super().__init__(ip_address)

    def set_horizontal_record_length(self, record_length: int, queue: bool=False):
        """
        Set horizontal timebase parameters.

        record_length: number of points to acquire (e.g. 1000)
        """
        if record_length not in (1000, 10_000, 100_000, 1_000_000, 10_000_000):
            raise ValueError("record_length must be one of 1000, 10k, 100k, 1M, 10M")
        command = f"HORizontal:RECOrdlength {record_length}"
        if queue:
            self.op_queue.append(command)
        else:
            self.scope.write(command)

    def setup(self, channel_configs, horizontal_scale, horizontal_position, trigger_config, reset=True, queue=False, sleep_time=3):
        if reset:
            self.reset(queue)
            self.set_current_datetime(queue)

        for ch_cfg in channel_configs:
            self.set_channel(**ch_cfg, queue=queue)
        
        # Waveform time will be 10*horizontal scale
        self.set_horizontal_scale(horizontal_scale, queue)
        self.set_horizontal_position(horizontal_position, queue)
        self.set_horizontal_record_length(10_000_000, queue)

        # Slope: RISE/FALL
        # Mode: NORMAL/AUTO
        self.set_trigger(**trigger_config, queue=queue)
        self.start_acquisition(queue)

        if not queue:
            # Wait for the scope to be ready
            time.sleep(sleep_time)


    def get_waveform(self, channel: int):
        """
        Retrieve waveform from CH<channel> and return (t, y) as numpy arrays.

        SCPI steps:
        - DATa:SOUrce CHn
        - DATa:ENCdg RIBinary; WFMOutpre:BN_Fmt RI; WFMOutpre:BYT_Nr 1; DATa:WIDth 1
        - Query WFMOutpre fields: NR_Pt, XINcr, XZEro, PT_Off, YZEro, YOFf, YMUlt
        - CURVe? and parse IEEE 488.2 definite-length block
        - y = (code - YOFF)*YMULT + YZERO
            t = XZERO + (i - PTOFF)*XINCR
        """
        import numpy as np

        if not (1 <= channel <= 4):
            raise ValueError("channel must be 1..4")

        ch = f"CH{channel}"

        # Keep responses simple (ignore if unsupported on this model)
        try:
            self.scope.write("HEADer OFF")
        except Exception:
            pass

        # Select source and a simple transfer encoding (signed 8-bit)
        self.scope.write(f"DATa:SOUrce {ch}")
        self.scope.write("DATa:ENCdg RIBinary")   # signed integer, big-endian representation
        self.scope.write("WFMOutpre:BN_Fmt RI")   # signed integer codes
        self.scope.write("WFMOutpre:BYT_Nr 1")    # 1 byte per point
        self.scope.write("DATa:WIDth 1")          # 1 byte per data word

        self.scope.write("DATa:STARt 1")         # NEW
        self.scope.write("DATa:STOP 1000000")  # NEW: large sentinel; scope will clamp to max

        # Query required preamble fields individually (robust across firmware)
        # NR_Pt sometimes appears as WFMPre:NR_Pt? on variants; keep a fallback.
        try:
            npts = int(self.scope.query("WFMOutpre:NR_Pt?").strip())
            print(npts)
        except Exception:
            npts = int(self.scope.query("WFMPre:NR_Pt?").strip())
            print(npts)

        xincr = float(self.scope.query("WFMOutpre:XINcr?").strip())
        xzero = float(self.scope.query("WFMOutpre:XZEro?").strip())
        ptoff = float(self.scope.query("WFMOutpre:PT_Off?").strip())
        yzero = float(self.scope.query("WFMOutpre:YZEro?").strip())
        yoff  = float(self.scope.query("WFMOutpre:YOFf?").strip())
        ymult = float(self.scope.query("WFMOutpre:YMUlt?").strip())

        # NEW
        self.scope.write(f"DATa:STARt 1")
        self.scope.write(f"DATa:STOP {npts}")
        
        # Ask for the waveform binary block and read raw bytes
        self.scope.write("CURVe?")
        blob = self.scope.read_raw()

        # Parse IEEE 488.2 definite-length block in 'blob'
        # Format: b'#' + d (ASCII digit count) + d digits (ASCII payload length) + payload + [optional terminator]
        if not blob or blob[0:1] != b"#":
            # Some links may insert a CR/LF; attempt a simple recovery if first byte is CR/LF
            i0 = 0
            while i0 < len(blob) and blob[i0:i0+1] in (b"\r", b"\n"):
                i0 += 1
            if i0 >= len(blob) or blob[i0:i0+1] != b"#":
                raise IOError(f"CURVe? response missing definite-length block header: {blob[:16]!r}")
            blob = blob[i0:]  # skip leading CR/LF

        if len(blob) < 2:
            raise IOError("Incomplete CURVe? block header")

        ndig = blob[1] - 48  # ASCII digit -> int
        if ndig <= 0:
            raise IOError(f"Unsupported block with ndigits={ndig}")
        header_len = 2 + ndig
        if len(blob) < header_len:
            raise IOError("Incomplete length field in CURVe? response")

        try:
            payload_len = int(blob[2:2+ndig].decode("ascii"))
        except Exception as e:
            raise IOError(f"Invalid payload length field in CURVe? response: {blob[2:2+ndig]!r}") from e

        total_needed = header_len + payload_len
        if len(blob) < total_needed:
            # Some VISA stacks may split reads; if this ever occurs, switch to chunked reads.
            # With pyvisa's read_raw(), you usually get the full message.
            raise IOError(f"Truncated CURVe? payload: expected {payload_len} bytes, got {len(blob)-header_len}")

        payload = blob[header_len:header_len+payload_len]

        # Interpret as signed 8-bit codes per our setup
        codes = np.frombuffer(payload, dtype=np.int8)

        # Mismatch can occur if DATa:STARt/STOP were set elsewhere; trim conservatively
        if codes.size != npts:
            n = min(npts, codes.size)
            codes = codes[:n]
            npts = n

        # Scale to physical units
        # y = (code - YOFF)*YMULT + YZERO
        # t = XZERO + (i - PTOFF)*XINCR
        y = (codes.astype(np.float64) - yoff) * ymult + yzero
        i = np.arange(npts, dtype=np.float64)
        t = xzero + (i - ptoff) * xincr

        return t, y
        
def test_scope(identifier):
    print(f"Testing scope for identifier: {identifier}")
    labels = ["GND_PROBE", "12V_PROBE"]

    with Scope(identifier) as scope:
        ident = scope.identify()
        print(f"\t=> {ident}")
        ident = "_".join([x.lower() for x in ident.split(',')[:3]])

        scope.setup(
            channel_configs=[
                {
                    "channel": 1,
                    "vertical_scale": 0.05,   # Volts/div
                    "vertical_position": -3.0,
                    "termination_fifty_ohms": True,
                    "label": labels[0],
                    "ac_coupling": False,
                    "enabled": True
                },
                {
                    "channel": 2,
                    "vertical_scale": 0.05,   # Volts/div
                    "vertical_position": -1.0,
                    "termination_fifty_ohms": False,
                    "label": labels[1],
                    "ac_coupling": True,
                    "enabled": True
                }
            ],
            horizontal_scale=500e-9,
            horizontal_position=0.0,
            trigger_config={
                "channel": 2,
                "level": 0.06,
                "slope": "RISE",
                "mode": "AUTO"
            },
            queue=True,
            reset=True,
        )
        scope.run_queue()
        time.sleep(1.0)  # let some triggers happen

        # # screen = scope.get_screen_png()
        for i, label in zip([1, 2], labels):
            print(f"Retrieving data from channel {i} ({label})")
            times, voltages = scope.get_waveform(channel=i)
            with open(f"{ident}_chan{i}.csv", "w") as f:
                f.write("channel,label,time,voltage\n")
                for t, v in zip(times, voltages):
                    f.write(f"{i},{label},{t},{v}\n")
            print(f"\t=> Channel {i} data saved to {ident}_chan{i}.csv")
        return ident

def main():
    test_scope(ip)

if __name__ == "__main__":
    main()
