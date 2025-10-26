> [!CAUTION]
> This is a basically untested mod! There are no guarantees of stability or safety, especially as this mod explicitly removes a safety check from the printer - the thermistor used in virtually all AD5M hotends is not meant to go past 300C and the ADC in the eboard MCU may also struggle with precision for such low resistance values. It is recommended to use a hotend with a different thermistor and a custom temp table for temperatures above 300C. Additionally, the other components and materials used in the AD5M may be insufficient for temperatures above 280C. When using this mod, always monitor the printer while it's active and check the hardware after use to ensure there is no degradation from high temperatures.

This is a firmware mod to disable the eboard temperature limit for the Adventurer 5M. Currently supported firmware versions are 2.4.5 through 3.1.9 (current at time of writing), or any version with control version 2.2.3.

## Installation

1) Download the most recent `.tgz` from the [releases page](https://github.com/a-johnston/ad5m_temp_limit_mod/releases) or follow the build steps below.
2) Copy the `.tgz` file (without unpacking it) to a FAT32-formatted USB flash drive.
3) Insert the flash drive into the printer while it's powered down.
4) Power on the printer to load the `.tgz` file and apply the patch.

## Building

0) Ensure `magick` (the CLI for imagemagick), `make`, and `tar` are available
1) Clone or download this repo
2) In the project's root folder, run `make`

## Verifying the patch

The eboard firmware included in this mod was patched using [Binary Ninja](https://binary.ninja/) but other tools such as [Ghidra](https://github.com/NationalSecurityAgency/ghidra) can also be used (or even a plain text editor if you're hard enough). The modded firmware patches out the check at address `0x08010330`.

The eboard firmware file is in the Intel hex format. Although this is a text format, it can be difficult to get clean diffs using normal text based tools such as git. Additionally, the free version of Binary Ninja only supports writing out binary files (the paid version supports plugins, including one that can output Intel hex format). To address both of these issues, I've also published an [intel hex CLI tool](https://github.com/a-johnston/intel_hex_tool/) which can convert between binary and intel hex formats as well as output concise diffs between two hex files. For example, here is the diff between the original and patched eboard files provided in this repo:

```
$ iht diff Eboard-20231012_original.hex Eboard-20231012.hex --disasm

@@ -0x08010330,2 +0x08010330,2 @@
+0046 : MOV R0, R0
-31D8 : BHI label[31]

@@ -0x08010336,2 +0x08010336,2 @@
+0046 : MOV R0, R0
-1A80 : STRH R2, R3, #0

@@ -0x0801039C,2 +0x0801039C,2 @@
+0046 : MOV R0, R0
-9BB2 : UXTH R3, R3

@@ -0x080103A0,4 +0x080103A0,4 @@
+00460046 : MOV R0, R0 / MOV R0, R0
-2B80C9D9 : STRH R3, R5, #0 / BLS label[C9]

@@ -0x080103AA,4 +0x080103AA,4 @@
+00460046 : MOV R0, R0 / MOV R0, R0
-02F027F9 : ?? / ??

@@ -0x080103B0,2 +0x080103B0,2 @@
+0046 : MOV R0, R0
-208B : LDRH R0, R4, #12

@@ -0x080103B6,4 +0x080103B6,4 @@
+00460046 : MOV R0, R0 / MOV R0, R0
-11702B80 : STRB R1, R2, #0 / STRH R3, R5, #0
```

While the disassembled output is simplified, it accurately shows which instructions have been converted to the no-op `MOV R0, R0`.

If using Binary Ninja, the raw binary file does not include offset or start address information. This can be read from the original hex file and included when converting the binary file:

```
$ iht info Eboard-20231012_original.hex

Info for Eboard-20231012_original.hex
  Type:         intel hex
  Start:        0x08015E7D
  Line endings: '\r\n' (dos)
  Chunks:
    Offset = 0x08010000 Length = 392 bytes
    (0x00 x 8)
    Offset = 0x08010190 Length = 33208 bytes

$ iht write Eboard-20231012.bin Eboard-20231012.hex --start=0x08015E7D --offset=0x08010000 --newline=dos
```
