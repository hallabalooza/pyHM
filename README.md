# pyHM

## Abstract

pyHM is a Python 3.5 implementation of simple home metering application based on SML (Smart Message Language), OBIS
(Object Identification System) and SQLite.
It receives SML telegrams from USB IR Write/Read interfaces, extracts OBIS informations from SML_GetListRes messages
contained in a telegram, stores these informations in a SQLite database and logs all events.

## General Execution

* install Python 3.5.x
* install Python modules
  [colorama](https://github.com/tartley/colorama),
  [colorlog](https://github.com/borntyping/python-colorlog),
  [pyserial](https://github.com/pyserial/pyserial) and
  [pyyaml](https://github.com/yaml/pyyaml),
   e.g. via [pip](https://github.com/pypa/pip)
* clone the repository pyHM into any directory <PYHM>
* create a PEM key and certificate file into this directory, e.g. via `openssl req -new -newkey rsa:4096 -x509 -subj "/C=us/ST=florida/L=orlando/O= /OU= /CN= " -days 365 -nodes -keyout your_own_key.pem -out your_own_cert.pem`
* edit *pyHM.cfg* to your needs
* start data acquisition
  * open a command line and change dir into *<PYHM>*
  * type `./pyHM_dattrc.sh start` or `pyHM_dattrc.bat` whether you're on Linux or Windows
* start web server
  * open a command line and change dir into *<PYHM>*
  * type `./pyHM_websrv.sh start` or `pyHM_websrv.bat` whether you're on Linux or Windows
* enjoy pyHM
* close web server
  * set focus on the command line running web server and press `STRG+C` or
  * run `./pyHM_websrv.sh stop` in another terminal
* close data acquisition
  * set focus on the command line running data acquisition and press `STRG+C` or
  * run `./pyHM_dattrc.sh stop` in another terminal

## Launch

### Fedberry 27.1-beta1 on Raspberry 3

* download [Fedberry 27.1-beta1](http://download.fedberry.org/?dir=releases/27/images/armhfp/27.1-beta1)
* write image on a SD Memory Card
* place SD Memory Card in [Raspberry 3](https://www.raspberrypi.org/)
* start up Raspberry 3 and follow the instructions, e.g. configuring a root password, creating a user *<USER>*, ...
* login as user *<USER>*
* install Python 3.5.x modules
  [colorama](https://github.com/tartley/colorama),
  [colorlog](https://github.com/borntyping/python-colorlog),
  [pyserial](https://github.com/pyserial/pyserial) and
  [pyyaml](https://github.com/yaml/pyyaml),
  e.g. via [dnfdragora](https://github.com/manatools/dnfdragora)
* install Linux application
  [screen](https://www.gnu.org/software/screen/manual/screen.html),
  e.g. via [dnfdragora](https://github.com/manatools/dnfdragora)
* configure a static IP address *<IPADDR>*
* copy or checkout pyHM and all submodules into a directory *<PYHM>* in the home directory of *<USER>*
* create a PEM key and certificate file into this directory, e.g. via `openssl req -new -newkey rsa:4096 -x509 -subj "/C=us/ST=florida/L=orlando/O= /OU= /CN= " -days 365 -nodes -keyout your_own_key.pem -out your_own_cert.pem`
* edit *pyHM.cfg* to your needs
* add the port configured in *pyHM.cfg* for the web server to the permanent configuration of the firewall
* create a file `/usr/lib/udev/rules.d/97-hm.rules` with following content
  ```
  # Meter01
  SUBSYSTEMS=="usb", ATTRS{idVendor}=="<VID>", ATTRS{idProduct}=="<PID>", ATTRS{serial}=="<SERIAL>", MODE="0666", SYMLINK+="hm_<SERIAL>"
  # Meter02
  SUBSYSTEMS=="usb", ATTRS{idVendor}=="<VID>", ATTRS{idProduct}=="<PID>", ATTRS{serial}=="<SERIAL>", MODE="0666", SYMLINK+="hm_<SERIAL>"
  # ...
  ```
  with *<VID>*, *<PID>* and *<SERIAL>* relating to the USB parameters of your specific USB IR adaptor
* create a file `/etc/systemd/system/pyHM_websrv.service` with following content (as root)
  ```
  [Unit]
  Description=pyHM web server
  Requires=network-online.target pyHM_dattrc.service
  After=network-online.target pyHM_dattrc.service

  [Service]
  Type=forking
  ExecStart=/usr/bin/screen -dmS pyHM_websrv /home/<USER>/<PYHM>/pyHM_websrv.sh start
  ExecStop=/home/<USER>/<PYHM>/pyHM_websrv.sh stop
  User=<USER>
  WorkingDirectory=/home/<USER>/<PYHM>

  [Install]
  WantedBy=multi-user.target
  ```
* create a file `/etc/systemd/system/pyHM_dattrc.service` with following content (as root)
  ```
  [Unit]
  Description=pyHM data trace

  [Service]
  Type=forking
  ExecStart=/usr/bin/screen -dmS pyHM_dattrc /home/<USER>/<PYHM>/pyHM_dattrc.sh start
  ExecStop=/home/<USER>/<PYHM>/pyHM_dattrc.sh stop
  User=<USER>
  WorkingDirectory=/home/<USER>/<PYHM>

  [Install]
  WantedBy=multi-user.target
  ```
* edit in file `/etc/selinux/config` the value of key `SELINUX` to `disabled` (as root)
* call `systemctl enable pyHM_websrv.service`
* call `systemctl enable pyHM_dattrc.service`
* restart the Raspberry 3
* login as *<USER>* and start a shell or connect from the shell of another PC via `ssh <USER>@<IPADDR>`
* call `screen -r pyHM_websrv` to attach the virtual shell where `pyHM_websrv` is running to the real shell; detach via `Ctrl+a,d`
* call `screen -r pyHM_dattrc` to attach the virtual shell where `pyHM_dattrc` is running to the real shell; detach via `Ctrl+a,d`
* logout or call `systemctl poweroff` or `systemctl reboot`
