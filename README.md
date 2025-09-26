This is a firmware mod to disable the eboard temperature limit for the Adventurer 5M. Currently supported firmware versions are 2.4.5 through 3.1.9 (current at time of writing), or any version with control sub-version 2.2.3.

## Reproducing initial commit

To help verify the files in this repo, it's possible to recreate the initial commit (`d938e485d3920`) and use git to check for differences to the official files.

The base firmware is version 3.1.5 and can be downloaded from the Flashforge website [here](https://flashforge-resource.oss-us-east-1.aliyuncs.com/AD5M%E5%9B%BA%E4%BB%B6/Adventurer5M-3.1.5-2.2.3-20250212.tgz). This base file and control folder have been unpacked into the repo.

## Verifying the patch

There are three versions of the eboard firmware included in this repo: the normal file has been patched, `Eboard-*_original.hex` is the original, and `Eboard-*_ghidra.hex` has been roundtripped through [Ghidra](https://github.com/NationalSecurityAgency/ghidra) (this is different from the original due to inconsistent record sizes in the original). The patch can be checked with `diff Eboard-20231012_ghidra.hex Eboard-20231012.hex`.

Additionally, a python tool is included for dumping the bytes of a given hex file. This can be used as an alternative to Ghidra for checking the roundtripped hex file.
