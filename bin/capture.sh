#!/bin/bash
TIMESTAMP=$(date +%s)

echo $TIMESTAMP > /tmp/$USER/start_timestamp
TAG=${1:-"csi_capture_$TIMESTAMP"}
DROOT="/tmp/$USER/$TAG"
[ -e $DROOT ] && echo "Destination directory already exists.  Playing it safe, exiting." && exit
echo "BEGIN $TAG"
if [ -e ]
rm -f /tmp/duncanfyfe/ttyUSB?/*
for tty in ttyUSB0 ttyUSB1 ttyUSB2 ttyUSB3; do
	[ -e "/dev/$tty" ] && ./capture.py $tty $TAG &
done
wait
mkdir $TAG
date +%s > /tmp/duncanfyfe/stop_timestamp
rsync -a /tmp/duncanfyfe/ttyUSB0 $TAG/ACTIVE_AP
rsync -a /tmp/duncanfyfe/ttyUSB1 $TAG/ACTIVE_STA
rsync -a /tmp/duncanfyfe/ttyUSB2 $TAG/PASSIVE_INTER
rsync -a /tmp/duncanfyfe/ttyUSB3 $TAG/PASSIVE_REF
echo "END $TAG"
