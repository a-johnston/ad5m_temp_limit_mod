#!/bin/sh
set -x

WORK_DIR=`dirname $0`
RUN_DIR="/opt/PROGRAM"

MACHINE=Adventurer5M
PID=0023

CHECH_ARCH=`uname -m`
if [ "${CHECH_ARCH}" != "armv7l" ];then
    echo "Machine architecture error."
    echo ${CHECH_ARCH}
    exit 1
fi

update_control()
{
	echo "update control"
	cd $WORK_DIR
	start_head="control-"
	end_tail=".tar.xz"
	ls -1t ${start_head}*${end_tail}
	if [ $? -eq 0 ];then
		file_name=`ls -1t ${start_head}*${end_tail} | head -n 1`
		version_length=`expr ${#file_name} - ${#start_head} - ${#end_tail}`
		control_version=${file_name:${#start_head}:${version_length}}
		echo "${control_version}"
		if [ ! -d ${RUN_DIR}/control ];then
			mkdir -p ${RUN_DIR}/control
		fi
		temp_dir=${RUN_DIR}/control/temp
		if [ -d ${temp_dir} ];then
			rm -rf ${temp_dir}
		fi
		mkdir -p ${temp_dir}
		tar -xvf ${file_name} -C ${temp_dir}
		sync
		cd ${temp_dir}
		md5sum -s -c md5sum.list
		if [ $? -eq 0 ];then
			cd ..
			ls | grep -v temp | xargs rm -rf
			sync
			mv temp ${control_version}
			sync
			cd ${control_version}
			#if [ -f run.sh ];then
			#	${RUN_DIR}/control/${control_version}/run.sh
			#fi
		else
			cd ..
			rm -rf temp
		fi
	fi
}

if [ ! -d ${RUN_DIR} ];then
	mkdir -p ${RUN_DIR}
fi

sync
cat $WORK_DIR/start.img > /dev/fb0

update_control

sync
cat $WORK_DIR/end.img > /dev/fb0

exit 0
