#!/bin/bash

# dependencies install
sudo apt-get install -y libzmq3-dev
if ! [ -x "$(command -v pip)" ]; then
  sudo apt-get install -y pip
fi
python -m pip install pyzmq

# create executable files
touch rpc_client.sh < python rpc/rpcclient.py $*
chmod +x rpc_client.sh
