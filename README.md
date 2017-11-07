# pyHM

## Abstract

pyHM is a Python 3.5 implementation of simple home metering application based on SML (Smart Message Language), OBIS
(Object Identification System) and SQLite.
It receives SML telegrams from USB IR Write/Read interfaces, extracts OBIS informations from SML_GetListRes messages
contained in a telegram, stores these informations in a SQLite database and logs all events.

## Execution

* install Python 3.5.x
* install Python modules `pyyaml` and `colorlog`, e.g. via `pip`
* clone the repository pyHM into any directory <PYHM>
* create a PEM file into this directory, e.g. via `OpenSSL`
* edit `pyHM.cfg` to your needs
* start data acquisition
  * open a command line and change dir into `<PYHM>`
  * type `./pyHM_dattrc.sh` or `pyHM_dattrc.bat` whether you're on Linux or Windows
* start web server
  * open a command line and change dir into `<PYHM>`
  * type `./pyHM_websrv.sh` or `pyHM_websrv.bat` whether you're on Linux or Windows
* enjoy pyHM
* close web server
  * set focus on the command line running web server
  * press `STRG+C`
* close data acquisition
  * set focus on the command line running data acquisition
  * press `STRG+C`
