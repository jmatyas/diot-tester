from artiq_tektronix_osc.driver import Tektronix4SeriesScope
import time
from pathlib import Path

ip = "192.168.95.106"

class Scope(Tektronix4SeriesScope):
    def __init__(self, ip_address: str):
        super().__init__(ip_address)
    
    def set_trigger_delay(self, delay_s: float | None, queue: bool = False):
        """
        Set trigger delay (seconds). Positive delay means the trigger event is placed
        delay_s after the left edge of the acquisition window.

        delay_s: seconds (e.g. 0.05 for 50 ms). Use 0 to disable delay.
        """
        if delay_s is None:
            return

        delay_s = float(delay_s)
        if delay_s < 0:
            raise ValueError("trigger_delay must be >= 0 seconds")

        cmd = f"HORizontal:DELay:TIMe {delay_s}"
        if queue:
            self.op_queue.append(cmd)
        else:
            self.scope.write(cmd)


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

    def set_vertical_offset(self, channel: int, offset_v: float, queue: bool = False):
        """
        Set vertical offset (in volts) for CH<channel>.
        """
        if not (1 <= channel <= 4):
            raise ValueError("channel must be 1..4")

        cmd = f"CH{channel}:OFFSet {float(offset_v)}"
        if queue:
            self.op_queue.append(cmd)
        else:
            self.scope.write(cmd)
       
    
    def set_channel_bandwidth(self, channel: int, bw, queue: bool = False):
        """
        Set analog channel bandwidth limit.

        Tek SCPI: CH<x>:BANdwidth {<NR3>|FULl}
        Example: CH1:BANDWIDTH 20  -> 20 MHz
                CH1:BANDWIDTH FULL -> no limit
        """
        if not (1 <= channel <= 4):
            raise ValueError("channel must be 1..4")

        if bw is None:
            return

        # Allow strings like "FULL"
        if isinstance(bw, str):
            if bw.strip().upper() in ("FULL", "FULl".upper()):
                arg = "FULl"
            else:
                raise ValueError('bw string must be "FULL" (or None)')
        else:
            # Accept either MHz (e.g. 20) OR Hz (e.g. 20e6) and normalize to MHz.
            bw_val = float(bw)
            bw_mhz = (bw_val / 1e6) if bw_val > 1e5 else bw_val
            arg = f"{bw_mhz:g}"

        cmd = f"CH{channel}:BANdwidth {arg}"
        if queue:
            self.op_queue.append(cmd)
        else:
            self.scope.write(cmd)


    def setup(self, channel_configs, horizontal_scale, horizontal_position, trigger_config, trigger_delay=None, reset=True, queue=False, sleep_time=3):
        if reset:
            self.reset(queue)
            self.set_current_datetime(queue)

        for ch_cfg in channel_configs:
            ch_cfg = dict(ch_cfg)  # local copy (we will pop extra options)

            v_off = ch_cfg.pop("vertical_offset", None)
            bw    = ch_cfg.pop("bandwidth", None)   # NEW

            self.set_channel(**ch_cfg, queue=queue)

            if v_off is not None:
                self.set_vertical_offset(ch_cfg["channel"], v_off, queue=queue)

            if bw is not None:
                self.set_channel_bandwidth(ch_cfg["channel"], bw, queue=queue)

        
        # Waveform time will be 10*horizontal scale
        self.set_horizontal_scale(horizontal_scale, queue)
        self.set_horizontal_position(horizontal_position, queue)
        self.set_horizontal_record_length(1_000_000, queue)

        # NEW: trigger delay
        self.set_trigger_delay(trigger_delay, queue=queue)

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
        self.scope.write("DATa:STOP 10000000")  # NEW: large sentinel; scope will clamp to max
        
        

        # Query required preamble fields individually (robust across firmware)
        # NR_Pt sometimes appears as WFMPre:NR_Pt? on variants; keep a fallback.
        try:
            npts = int(self.scope.query("WFMOutpre:NR_Pt?").strip())
            src = "WFMOutpre"
        except Exception:
            npts = int(self.scope.query("WFMPre:NR_Pt?").strip())
            src = "WFMPre"

        print(f"[NR_Pt] {src}: {npts:.3e}")

        xincr = float(self.scope.query("WFMOutpre:XINcr?").strip())
        xzero = float(self.scope.query("WFMOutpre:XZEro?").strip())
        ptoff = float(self.scope.query("WFMOutpre:PT_Off?").strip())
        yzero = float(self.scope.query("WFMOutpre:YZEro?").strip())
        yoff  = float(self.scope.query("WFMOutpre:YOFf?").strip())
        ymult = float(self.scope.query("WFMOutpre:YMUlt?").strip())

        # NEW
        #self.scope.write(f"DATa:STARt 1")
        #self.scope.write(f"DATa:STOP {npts}")
        
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
        print("y min/max:", float(np.min(y)), float(np.max(y)))
        i = np.arange(npts, dtype=np.float64)
        t = xzero + (i - ptoff) * xincr

        return t, y
        
def test_scope(identifier, outdir=None, base_name=None,vertical_scale_ch1: float | None = None,vertical_scale_ch2: float | None = None):
    outdir = Path(outdir) if outdir is not None else Path(".")
    outdir.mkdir(parents=True, exist_ok=True)

    file_base = base_name  # if provided, use it

    print(f"Testing scope for identifier: {identifier}")
    labels = ["Ch1", "Ch2"]
    vdiv_ch1 = 0.005 if vertical_scale_ch1 is None else float(vertical_scale_ch1)
    vdiv_ch2 = 0.005 if vertical_scale_ch2 is None else float(vertical_scale_ch2)

    with Scope(identifier) as scope:
        ident = scope.identify()
        print(f"\t=> {ident}")
        ident = "_".join([x.lower() for x in ident.split(',')[:3]])

        scope.setup(
            channel_configs=[
                {
                    "channel": 1,
                    "vertical_scale": vdiv_ch1,   # 0.001
                    "vertical_position":0, #1.16
                    "vertical_offset" : 0,   
                    "bandwidth": 20,
                    "termination_fifty_ohms":False,
                    "label": labels[0],
                    "ac_coupling": True,
                    "enabled": True
                },
                {
                    "channel": 2,
                    "vertical_scale":  vdiv_ch2,   # Volts/div #for DC =0.2 #for AC=0.02
                    "vertical_position": 0, #for DC = -4.0 #for AC=0
                    "vertical_offset":0,
                    "bandwidth": 20, 
                    "termination_fifty_ohms": False,
                    "label": labels[1],
                    "ac_coupling": True,
                    "enabled": True
                }
            ],
            horizontal_scale=0.01, #0.002
            horizontal_position=0.0,
            trigger_config={
                "channel": 1,
                "level": 0, 
                "slope": "RISE",
                "mode": "NORMAL"
            },
            trigger_delay=1, #0.05 for AC coupling
            queue=True,
            reset=True,
        )
        scope.run_queue()
       
        time.sleep(3.0)  # let some triggers happen

        # screen = scope.get_screen_png()
        for i, label in zip([1, 2], labels):
            print(f"Retrieving data from channel {i} ({label})")
            times, voltages = scope.get_waveform(channel=i)
            fname_base = file_base if file_base is not None else ident
            outpath = outdir / f"{fname_base}_chan{i}.csv"

            with open(outpath, "w") as f:
                f.write("channel,label,time,voltage\n")
                for t, v in zip(times, voltages):
                    f.write(f"{i},{label},{t},{v}\n")

            print(f"\t=> Channel {i} data saved to {outpath}")
            n_csv = sum(1 for _ in open(outpath)) - 1  # minus header
            print(f"\t=> CSV samples: {n_csv:.3e}")
        return ident

def dump_current_scope_to_csv(identifier, outdir=None, base_name=None, channels=(1, 2)):
    """
    Dump the currently displayed/acquired waveform(s) from the scope to CSV.
    Assumes the acquisition was configured and triggered manually on the scope UI.
    """
    outdir = Path(outdir) if outdir is not None else Path(".")
    outdir.mkdir(parents=True, exist_ok=True)

    labels = {1: "Ch1", 2: "Ch2", 3: "Ch3", 4: "Ch4"}

    with Scope(identifier) as scope:
        ident = scope.identify()
        print(f"\t=> {ident}")
        ident_s = "_".join([x.lower() for x in ident.split(",")[:3]])
        fname_base = base_name if base_name is not None else ident_s

        # Freeze acquisition so the record does not change during transfer
        try:
            scope.scope.write("ACQuire:STATE STOP")
        except Exception:
            pass

        for ch in channels:
            print(f"Retrieving data from channel {ch} ({labels.get(ch, f'Ch{ch}')})")
            t, y = scope.get_waveform(channel=ch)
            outpath = outdir / f"{fname_base}_chan{ch}.csv"

            with open(outpath, "w") as f:
                f.write("channel,label,time,voltage\n")
                for ti, yi in zip(t, y):
                    f.write(f"{ch},{labels.get(ch, f'Ch{ch}')},{ti},{yi}\n")

            print(f"\t=> Channel {ch} data saved to {outpath}")


def main():
    test_scope(ip)

if __name__ == "__main__":
    main()
