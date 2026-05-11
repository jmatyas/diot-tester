VARIANT ?= diot-tester-fastino

ifeq ($(VARIANT),sinara-tester-fastino-high)
  DESC := desc/kasli_fastino_high.json
else ifeq ($(VARIANT),sinara-tester-fastino-low)
  DESC := desc/kasli_fastino_low.json
else ifeq ($(VARIANT),diot-tester-fastino)
  DESC := desc/kasli_diot_fastino.json
else
  $(error Unknown VARIANT: "$(VARIANT)". Supported: sinara-tester-fastino-high, sinara-tester-fastino-low, diot-tester-fastino)
endif

.PHONY: help build build-storage flash flash-storage load

help:  ## Show available targets
	@awk 'BEGIN {FS = ":.*##"; printf "Usage: make <target>\n\nTargets:\n"} \
	    /^[a-zA-Z_-]+:.*?##/ { printf "  %-16s %s\n", $$1, $$2 }' \
	    $(MAKEFILE_LIST)

build:  ## Full build: gateware, kernels, storage image
	python -m artiq.gateware.targets.kasli --output-dir build $(DESC)
	artiq_ddb_template -o build/$(VARIANT)/device_db.py $(DESC)
	$(MAKE) build-storage

build-storage:  ## Compile kernels + storage image (no gateware, needs existing device_db.py)
	artiq_compile --device-db build/$(VARIANT)/device_db.py -o build/$(VARIANT)/startup.elf experiments/startup.py
	artiq_compile --device-db build/$(VARIANT)/device_db.py -o build/$(VARIANT)/idle.elf experiments/fastino_square.py
	artiq_mkfs -s ip 192.168.95.70 \
	    -f idle_kernel build/$(VARIANT)/idle.elf \
	    -f startup_kernel build/$(VARIANT)/startup.elf \
	    build/$(VARIANT)/storage.img

flash:  ## Erase and flash gateware + firmware + storage
	artiq_flash -t kasli --srcbuild -d build/$(VARIANT) \
	    -f build/$(VARIANT)/storage.img \
	    erase=firmware,bootloader,gateware,storage \
	    write=firmware,bootloader,gateware,storage load

flash-storage:  ## Flash storage partition only
	artiq_flash -t kasli --srcbuild -d build/$(VARIANT) \
	    -f build/$(VARIANT)/storage.img \
	    erase=storage \
	    write=storage load

load:  ## Load bitstream to FPGA over USB (no flash write)
	artiq_flash -t kasli --srcbuild -d build/$(VARIANT) load
