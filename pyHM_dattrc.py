# pyHM
# Copyright (C) 2017  Hallabalooza
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this program. If not, see
# <http://www.gnu.org/licenses/>.

########################################################################################################################
########################################################################################################################
########################################################################################################################

import pyLOG
import pyOBIS
import pySML
import datetime
import os
import re
import serial, serial.threaded
import signal
import sqlite3
import threading
import traceback
import time
import yaml

from collections import OrderedDict

########################################################################################################################
########################################################################################################################
########################################################################################################################

class HM_DatTrc_Exception(Exception):
  """
  @brief   HM data tracing exception class.
  """

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __init__(self, Mssg=None):
    """
    @brief   Constructor.
    @param   Mssg   The Exception message.
    """
    self._modl = inspect.stack()[1][0].f_locals["self"].__class__.__module__
    self._clss = inspect.stack()[1][0].f_locals["self"].__class__.__name__
    self._mthd = inspect.stack()[1][0].f_code.co_name
    self._mssg = None
    if   ( Mssg == None ): self._mssg = "{}.{}.{}".format(self._modl, self._clss, self._mthd)
    else                 : self._mssg = "{}.{}.{}: {}".format(self._modl, self._clss, self._mthd, {True:"---", False:Mssg}[Mssg==None])

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __str__(self):
    """
    @brief   Prints a nicely string representation.
    """
    return repr(self._mssg)

########################################################################################################################

class HM_DatTrc_Sql:
  """
  @brief   HM data tracing SQL access class.
  """

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __init__(self, idf, cfg):
    """
    @brief   Constructor.
    @param   idf   A HM meter identifier.
    @param   cfg   A HM meter configuration.
    """
    self.__idf                 = idf
    self.__cfg                 = cfg
    self.__log                 = pyLOG.Log(self.__cfg["logref"])
    self.__sql_con             = sqlite3.connect(self.__cfg["sqldb"])
    self.__sql_con.row_factory = sqlite3.Row
    self.__sql_cur             = self.__sql_con.cursor()
    self.__sql_cnt             = 0
    self.__sql_sve             = False
    self.__tab_meters          = dict()
    self.__tab_units           = dict()
    self.__tab_obis            = dict()
    self.__tab_tstamps         = OrderedDict()
    self.__max_tstamps         = 5
    self.__obs                 = pyOBIS.OBIS()

    self.__log.log_callinfo()

    # setup + read basic tables
    # - meters
    self.__sql_cur.execute("CREATE TABLE IF NOT EXISTS b_METERS (PK INTEGER PRIMARY KEY AUTOINCREMENT, value, description, UNIQUE(value));")
    self.__sql_cur.execute("SELECT * FROM b_METERS WHERE value == ?;", [idf])
    for i, row in enumerate(self.__sql_cur.fetchall()):
      self.__tab_meters[row["value"]] = row["PK"]

    # - units
    self.__sql_cur.execute("CREATE TABLE IF NOT EXISTS b_UNITS (PK INTEGER PRIMARY KEY AUTOINCREMENT, value, description, UNIQUE(value));")
    self.__sql_cur.execute("SELECT * FROM b_UNITS;")
    for i, row in enumerate(self.__sql_cur.fetchall()):
      self.__tab_units[row["value"]] = row["PK"]
    # - obis
    self.__sql_cur.execute("CREATE TABLE IF NOT EXISTS b_OBIS (PK INTEGER PRIMARY KEY AUTOINCREMENT, value, description, UNIQUE(value));")
    self.__sql_cur.execute("SELECT * FROM b_OBIS;")
    for i, row in enumerate(self.__sql_cur.fetchall()):
      self.__tab_obis[row["value"]] = row["PK"]

    # check for measure tables
    # - timestamps
    self.__sql_cur.execute("CREATE TABLE IF NOT EXISTS m_TIMESTAMPS (PK INTEGER PRIMARY KEY AUTOINCREMENT, value, UNIQUE(value));")
    self.__sql_cur.execute("SELECT * FROM (SELECT * FROM m_TIMESTAMPS ORDER BY value DESC LIMIT ?) ORDER BY value ASC;", [self.__max_tstamps])
    for i, row in enumerate(self.__sql_cur.fetchall()):
      self.__tab_tstamps[row["value"]] = row["PK"]
    # - points
    self.__sql_cur.execute("CREATE TABLE IF NOT EXISTS m_POINTS (PK INTEGER PRIMARY KEY AUTOINCREMENT, pk_timestamp, pk_meter, pk_obis, pk_unit, value, UNIQUE(pk_meter, pk_obis, pk_unit, value));")

    # check for views
    self.__create_view()

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __del__(self):
    """
    @brief   Destructor.
    """
    self.__log.log_callinfo()
    self.__sql_con.commit()
    self.__sql_con.close()

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __create_view(self):
    """
    @brief   Create views per meter if not exists.
    """
    try:
      self.__sql_cur.execute("""CREATE VIEW IF NOT EXISTS v_{} AS SELECT mt.value AS timestamp, bo.value AS obis, bo.description AS obis_desc, bu.value AS unit, bu.description AS unit_desc, mp.value AS value
                                FROM m_POINTS mp
                                  INNER JOIN m_TIMESTAMPS mt ON (mp.pk_timestamp = mt.pk)
                                  INNER JOIN b_OBIS       bo ON (mp.pk_obis      = bo.pk)
                                  INNER JOIN b_UNITS      bu ON (mp.pk_unit      = bu.pk)
                                WHERE mp.pk_meter=={}
                                ORDER BY timestamp, obis;
                             """.format(self.__idf, self.__tab_meters[self.__idf])
                            )
    except:
      pass

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def insert(self, timestamp, meter, obis, unit, value):
    """
    @brief   Insert a data tuple into SQL database.
    @param   timestamp   The timestamp.
    @param   meter       The HM meter identifier.
    @param   obis        The OBIS code.
    @param   unit        The unit.
    @param   value       The value.
    """
    self.__log.log_callinfo()

    if ( unit == None ):
      unit = 0xFF

    if ( meter != self.__idf ):
      raise HM_DatTrc_Exception("passed meter != configured meter")

    if ( meter != None and meter not in self.__tab_meters ):
      self.__sql_sve = True
      try:
        self.__sql_cur.execute("INSERT INTO b_METERS (value, description) VALUES (?, ?);", [meter, self.__cfg["note"]])
        self.__tab_meters[meter] = self.__sql_cur.lastrowid
      except sqlite3.IntegrityError:
        self.__sql_cur.execute("SELECT * FROM b_UNITS;")
        for i, row in enumerate(self.__sql_cur.fetchall()):
          self.__tab_units[row["value"]] = row["PK"]

    if ( unit != None and unit not in self.__tab_units ):
      self.__sql_sve = True
      try:
        self.__sql_cur.execute("INSERT INTO b_UNITS (value, description) VALUES (?, ?);", [unit, self.__obs.getUnit(unit)["native"]])
        self.__tab_units[unit] = self.__sql_cur.lastrowid
      except sqlite3.IntegrityError:
        self.__sql_cur.execute("SELECT * FROM b_UNITS;")
        for i, row in enumerate(self.__sql_cur.fetchall()):
          self.__tab_units[row["value"]] = row["PK"]

    if ( obis != None and obis not in self.__tab_obis ):
      self.__sql_sve = True
      try:
        self.__sql_cur.execute("INSERT INTO b_OBIS (value, description) VALUES (?, ?);", [obis, self.__obs.getDescr(obis)["descr"]])
        self.__tab_obis[obis] = self.__sql_cur.lastrowid
      except sqlite3.IntegrityError:
        self.__sql_cur.execute("SELECT * FROM b_OBIS;")
        for i, row in enumerate(self.__sql_cur.fetchall()):
          self.__tab_obis[row["value"]] = row["PK"]

    pk_tstamp = None
    pk_meter  = self.__tab_meters[meter]
    pk_obis   = self.__tab_obis[obis]
    pk_unit   = self.__tab_units[unit]
    pk_point  = None

    try:
      pk_tstamp = self.__tab_tstamps[timestamp]
      self.__sql_cur.execute("INSERT INTO m_POINTS (pk_timestamp, pk_meter, pk_obis, pk_unit, value) VALUES (?, ?, ?, ?, ?);", [pk_tstamp, pk_meter, pk_obis, pk_unit, value])
    except sqlite3.IntegrityError:
      pass
    except KeyError: # => timestamp
      try:
        self.__sql_cur.execute("INSERT INTO m_POINTS (pk_timestamp, pk_meter, pk_obis, pk_unit, value) VALUES (?, ?, ?, ?, ?);", [None, pk_meter, pk_obis, pk_unit, value])
        pk_point = self.__sql_cur.lastrowid
      except sqlite3.IntegrityError:
        pass
      else:
        try:
          self.__sql_cur.execute("INSERT INTO m_TIMESTAMPS (value) VALUES (?);", [timestamp.isoformat()])
          self.__tab_tstamps[timestamp] = self.__sql_cur.lastrowid
        except sqlite3.IntegrityError:
          self.__sql_cur.execute("SELECT * FROM b_TIMESTAMPS WHERE value == ?;", [timestamp.isoformat()])
          for i, row in enumerate(self.__sql_cur.fetchall()):
            self.__tab_tstamps[row["value"]] = row["PK"]
        pk_tstamp = self.__tab_tstamps[timestamp]
        self.__sql_cur.execute("UPDATE m_POINTS SET pk_timestamp=? WHERE PK=?", [pk_tstamp, pk_point])

    # maintain tstamps cache
    while ( len(self.__tab_tstamps) > self.__max_tstamps ):
      self.__tab_tstamps.popitem(last=False)

    # commit
    if ( self.__sql_cnt % 10 == 0 or self.__sql_sve == True ):
      self.__create_view()
      self.__sql_con.commit()
      self.__sql_cnt = 0
      self.__sql_sve = False

########################################################################################################################

class HM_DatTrc_SMLPacket(serial.threaded.Protocol):
  """
  @brief   HM data tracing SML packet serial receive class.
  """

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __init__(self, idf, cfg):
    """
    @brief   Constructor.
    @param   idf   A HM meter identifier.
    @param   cfg   A HM meter configuration.
    """
    self.__idf     = idf
    self.__cfg     = cfg
    self.__sql     = None
    self.__alv     = None
    self.__deb     = 0     # debunce counter
    self.__cnt     = 0     # received packet counter
    self.__log     = pyLOG.Log(self.__cfg["logref"])
    self.buffer    = bytearray()
    self.transport = None

    self.__log.log_callinfo()

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def connection_made(self, transport):
    """
    @brief   Stores transport.
    @param   transport    The instance used to write to serial port.
    """
    self.__log.log_callinfo()
    self.transport = transport

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def connection_lost(self, exc):
    """
    @brief   Forgets transport.
    @param   exc   Exception if connection was terminated by error else None.
    """
    self.__log.log_callinfo()
    self.transport = None
    super(HM_DatTrc_SMLPacket, self).connection_lost(exc)

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def data_received(self, data):
    """
    @brief   Buffer receives data and searchs for SML_Telegram terminators, when found, call handle_packet().
    @param   data   Bytes received via serial port.
    """
    self.__log.log_callinfo()
    self.buffer.extend(data)
    packets = [packet for packet in re.finditer(bytes("(?<!\x1b\x1b\x1b\x1b)\x1b\x1b\x1b\x1b\x01\x01\x01\x01.*?(?<!\x1b\x1b\x1b\x1b)\x1b\x1b\x1b\x1b\x1a(\x00|\x01|\x02|\x03)..".encode("ascii")), self.buffer, re.DOTALL)]
    if ( packets != [] ):
      for packet in packets:
        self.handle_packet(self.buffer[packet.start():packet.end()])
      del self.buffer[:packets[-1].end()]

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def prepare(self):
    """
    @brief   Prepare the processing of completely received packest. This is firstly called in a threads run method.
    """
    self.__log.log_callinfo()
    self.__sql = HM_DatTrc_Sql(self.__idf, self.__cfg)
    self.__sql.insert(datetime.datetime.now(), self.__idf, 0xFFFFFFFFFFFF, 0xFF, "RESET")

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def disperse(self):
    """
    @brief   Disperse the processing of completely received packest. This is lastly called in a threads run method.
    """
    self.__log.log_callinfo()
    del self.__sql

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def handle_packet(self, packet):
    """
    @brief   Process a completely received packet. This is repetitive called in a threads run method.
    @param   packet   A SML_Telegram.
    """
    self.__log.log_callinfo()
    try:
      telegram      = pySML.SML_Telegram()
      telegram.data = packet
      dat           = {}
      ts            = datetime.datetime.now()
      for msg in telegram.msg:
        if ( isinstance(msg.MessageBody.Element, pySML.SML_GetListRes) ):
          self.__deb = self.__deb + 1
          self.__cnt = self.__cnt + 1
          for i,val in enumerate(msg.MessageBody.Element.ValList.valu):
            #vStatus = val.Status.Element.valu
            vObis   = int(val.ObjName.valu.hex(), 16)
            vUnit   = val.Unit.valu
            vScaler = val.Scaler.valu
            vValue  = val.Value.Element.valu
            if ( vObis not in self.__cfg["filter"] ):
              if ( None == self.__alv ):
                self.__alv = vObis
              if ( vObis == self.__alv and 10 == self.__deb ):
                self.__log.log(pyLOG.LogLvl.INFO, "received packet ({:010})".format(self.__cnt))
                self.__deb = 0
              if ( None != vValue and isinstance(vValue, bytearray) ):
                try   : vValue = "\""+vValue.decode("utf-8")+"\""
                except: vValue = bytes(vValue)
              else:
                if ( None != vScaler ):
                  if   ( 0 > vScaler ): vValue = vValue / (10*(-vScaler))
                  else                : vValue = vValue * (10**vScaler)
              self.__sql.insert(ts, self.__idf, vObis, vUnit, vValue)
    except Exception as e:
      self.__log.log(pyLOG.LogLvl.ERROR, "\n{}\n{}".format(e, packet))

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __call__(self):
    """
    @brief   Call operator.
    """
    self.__log.log_callinfo()
    return self

########################################################################################################################

class HM_DatTrc_ReaderThread(serial.threaded.ReaderThread):
  """
  @brief   Customized version of serial.threaded.ReaderThread, that calls specific protocol_factory methods at the
           beginning and at the end of the receive thread.
  """

  def __init__(self, serial_instance, protocol_factory):
    """
    @brief   Constructor.
    @param   serial_instance    Serial port instance (opened) to be used.
    @param   protocol_factory   A callable that returns a Protocol instance.
    """
    super(HM_DatTrc_ReaderThread, self).__init__(serial_instance, protocol_factory)
    self.__stop = threading.Event()

  def close(self):
    """
    @brief   Close the serial port and exit reader thread.
    """
    if ( None != self.protocol ):
      self.__stop.set()
    super(HM_DatTrc_ReaderThread, self).close()

  def run(self):
    """
    @brief   The actual reader loop driven by the thread.
    """
    if ( None == self.protocol ):
      if ( not hasattr(self.serial, 'cancel_read') ):
        self.serial.timeout = 1
      self.protocol = self.protocol_factory()
      self.protocol.prepare()
      try:
        self.protocol.connection_made(self)
      except Exception as e:
        self.alive = False
        self.protocol.connection_lost(e)
        self._connection_made.set()
        return
      error = None
      self._connection_made.set()
      while ( self.alive and self.serial.is_open ):
        try:
          # read all that is there or wait for one byte (blocking)
          data = self.serial.read(self.serial.in_waiting or 1)
        except serial.SerialException as e:
          # probably some I/O problem such as disconnected USB serial
          # adapters -> exit
          error = e
          break
        else:
          if ( data ):
            # make a separated try-except for called used code
            try:
              self.protocol.data_received(data)
            except Exception as e:
              error = e
              break
        if ( True == self.__stop.isSet() ):
          self.protocol.disperse()
          break
      self.alive = False
      self.protocol.connection_lost(error)
      self.protocol = None

########################################################################################################################

class HM_DatTrc:
  """
  @brief   HM data tracing main class.
  """

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __init__(self, cfg):
    """
    @brief   Constructor.
    @param   cfg   HM configuration.
    """
    self.__cfg        = cfg
    self.__log        = pyLOG.Log(self.__cfg["general"]["logref"])
    self.__thd        = {}

    self.map_bytesize = {5:serial.FIVEBITS, 6:serial.SIXBITS, 7:serial.SEVENBITS, 8:serial.EIGHTBITS}
    self.map_stopbits = {1:serial.STOPBITS_ONE, 15:serial.STOPBITS_ONE_POINT_FIVE, 2:serial.STOPBITS_TWO}
    self.map_parity   = {"none":serial.PARITY_NONE, "even":serial.PARITY_EVEN, "odd":serial.PARITY_ODD, "mark":serial.PARITY_MARK, "space":serial.PARITY_SPACE}

    self.__log.log_callinfo()

    for idf_meter, cfg_meter in self.__cfg["meters"].items():
      self.__log.log(pyLOG.LogLvl.INFO, "configuring meter '{}' started".format(idf_meter))
      try:
        self.__thd[idf_meter] = HM_DatTrc_ReaderThread(serial.Serial(port    =    cfg_meter["serial"][0],
                                                                     baudrate=    cfg_meter["serial"][1],
                                                                     bytesize=self.map_bytesize[cfg_meter["serial"][2]],
                                                                     parity  =self.map_parity[cfg_meter["serial"][4]],
                                                                     stopbits=self.map_stopbits[cfg_meter["serial"][3]],
                                                                     timeout =0),
                                                       HM_DatTrc_SMLPacket(idf_meter, cfg_meter)
                                                      )
        self.__thd[idf_meter].start()
        for tk,tv in self.__thd.items():
          self.__log.log(pyLOG.LogLvl.INFO, "  receive thread '{}' started".format(tv))
        self.__log.log(pyLOG.LogLvl.INFO, "configuring meter '{}' done".format(idf_meter))
      except:
        self.__log.log(pyLOG.LogLvl.ERROR, "configuring meter '{}' failed".format(idf_meter))
        self.__log.log(pyLOG.LogLvl.ERROR, "{}".format(traceback.format_exc()))

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def isalive(self):
    """
    @brief   Returns whether a HM_DatTrc_ReaderThread is running or not.
    """
    for tk,tv in self.__thd.items():
      if ( True == tv.alive ): return True
    return False

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def stop(self):
    """
    @brief   Trigger exiting threads.
    """
    self.__log.log_callinfo()
    for tk,tv in self.__thd.items():
      self.__log.log(pyLOG.LogLvl.INFO, "deconfiguring meter '{}' started".format(tk))
      tv.close()
      self.__log.log(pyLOG.LogLvl.INFO, "  receive thread '{}' stopped".format(tv))
      self.__log.log(pyLOG.LogLvl.INFO, "deconfiguring meter '{}' done".format(tk))

########################################################################################################################

def signal_handler(signal, frame):
  """
  @brief   Application interrupt handler function.
  """
  global o_dattrc
  o_dattrc.stop()
  while ( True == o_dattrc.isalive() ):
    time.sleep(0.1)
  os._exit(1)

########################################################################################################################
########################################################################################################################
########################################################################################################################

if ( __name__ == '__main__' ):

  with ( open("pyHM.cfg", "r") ) as fhdl:
    cfg = yaml.load(fhdl.read())

  signal.signal(signal.SIGINT, signal_handler)
  pyLOG.LogInit(cfg["general"]["logger"])
  o_dattrc = HM_DatTrc(cfg)

  while ( True ):
    time.sleep(30)
