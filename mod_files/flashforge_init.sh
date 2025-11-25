#!/bin/bash
set -euxo pipefail

BASE_DIR=`dirname $0`
SCREENS=${BASE_DIR}/screens
state=0

trap on_exit EXIT

on_exit() {
    if [ $state -eq 0 ];then
        cat ${SCREENS}/fail.img > /dev/fb0
    fi
    if [ $state -eq 1 ];then
        cat ${SCREENS}/iap_fail.img > /dev/fb0
    fi
    if [ $state -eq 2 ];then
        cat ${SCREENS}/end.img > /dev/fb0
    fi
}

TARGET_VERSION="2.2.3"
CONTROL_DIR="/opt/PROGRAM/control/${TARGET_VERSION}"

EBOARD_FILE="${CONTROL_DIR}/Eboard-20231012.hex"
ORIGINAL_MD5="d378a3ad94da99d72a854ff20de356aa"
NEW_MD5="1697c5d3044c8b8eac4875c4a5ed6118"

cat ${SCREENS}/start.img > /dev/fb0

if [ ! -d "${CONTROL_DIR}" ];then
    echo "Need control version ${TARGET_VERSION}, quitting without patching"
    exit 1
fi
if [ ! -f "${CONTROL_DIR}/IAPCommand" ];then
    echo "Missing IAPCommand, quitting without patching"
    exit 1
fi
if [ ! -f "${EBOARD_FILE}" ];then
    echo "Missing base firmware, quitting without patching"
    exit 1
fi

echo "Checking original file"
echo "${ORIGINAL_MD5}  ${EBOARD_FILE}" | md5sum -c

echo "Creating patched file"
python ${BASE_DIR}/scripts/intel_hex_tool.py write ${EBOARD_FILE} ${EBOARD_FILE}.new --patch ${BASE_DIR}/patch.txt
sync

echo "Checking patched file"
echo "${NEW_MD5}  ${EBOARD_FILE}.new" | md5sum -c

echo "Applying patch"
mv ${EBOARD_FILE} ${EBOARD_FILE}.old
mv ${EBOARD_FILE}.new ${EBOARD_FILE}
chmod a+x $WORK_DIR/IAPCommand
sync
${CONTROL_DIR}/IAPCommand ${EBOARD_FILE} /dev/ttyS1

sync
echo "Finished upgrade"

exit 0
