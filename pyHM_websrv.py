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
import datetime
import http.server
import os
import random
import signal
import ssl
import sqlite3
import sys
import threading
import traceback
import time
import yaml
import urllib.parse
import pprint

########################################################################################################################
########################################################################################################################
########################################################################################################################

class HM_WebSrv_Sql:
  """
  @brief   HM web server SQL access class.
  """

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __init__(self, cfg):
    """
    @brief   Constructor.
    @param   cfg   A HM web server configuration.
    """
    self.__cfg                 = cfg
    self.__log                 = pyLOG.Log(self.__cfg["logref"])
    self.__sql_con             = sqlite3.connect(self.__cfg["sqldb"])
    self.__sql_con.row_factory = sqlite3.Row
    self.__sql_cur             = self.__sql_con.cursor()
    self.__tab_meters          = dict()
    self.__tab_units           = dict()
    self.__tab_obis            = dict()
    self.__tab_obisunits       = dict()

    self.__log.log_callinfo()
    self.update()

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __del__(self):
    """
    @brief   Destructor.
    """
    self.__log.log_callinfo()
    self.__sql_con.close()

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def update(self):
    """
    @brief   Update lists of basic informations.
    """
    self.__log.log_callinfo()
    # read basic tables
    # - meters
    self.__sql_cur.execute("SELECT * FROM b_METERS;")
    for i, row in enumerate(self.__sql_cur.fetchall()):
      self.__tab_meters[row["value"]] = {"key":i, "dsc":row["description"]}
    # - units
    self.__sql_cur.execute("SELECT * FROM b_UNITS;")
    for i, row in enumerate(self.__sql_cur.fetchall()):
      self.__tab_units[row["value"]] = {"key":i, "dsc":row["description"].decode("ascii", "ignore")}
    # - obis
    self.__sql_cur.execute("SELECT * FROM b_OBIS;")
    for i, row in enumerate(self.__sql_cur.fetchall()):
      self.__tab_obis[row["value"]] = {"key":i, "dsc":row["description"].decode("ascii", "ignore")}
    for k,v in self.__tab_obis.items():
      self.__sql_cur.execute("SELECT DISTINCT description FROM m_POINTS INNER JOIN b_UNITS ON (b_UNITS.PK=m_POINTS.pk_unit) WHERE m_POINTS.pk_obis == {};".format(v["key"]))
      self.__tab_obis[k]["unit"] = "---"
      for i, row in enumerate(self.__sql_cur.fetchall()):
        if   i == 0: self.__tab_obis[k]["unit"] = row["description"].decode("ascii", "ignore")
        else       : self.__log.log(pyLOG.LogLvl.ERROR, "Multiple units found for OBIS ''{}.".format(k))

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def extract(self, meter, dtf, dtu, enp, obis=[]):
    """
    @brief   Insert a data tuple into SQL database.
    @param   dtf   datetime from
    @param   dtu   datetime until.
    @param   enp   every nth point.
    """
    self.__log.log_callinfo()

    data = {}
    try:
      self.__sql_cur.execute("SELECT * FROM v_{} WHERE (timestamp BETWEEN '{}' AND '{}' ) AND (OBIS IN ({})) ORDER BY timestamp;".format(meter, dtf, dtu, ",".join(obis)))
      for i, row in enumerate(self.__sql_cur.fetchall()):
        if ( row["obis"] not in data ):
          data[row["obis"]] = {"x":[row["timestamp"]], "y":[row["value"]], "u":[row["unit"]], "c":1}
        else:
          if ( (data[row["obis"]]["c"] % enp) == 0 ):
            data[row["obis"]]["x"].append(row["timestamp"])
            data[row["obis"]]["y"].append(row["value"])
            data[row["obis"]]["u"].append(row["unit"])
            data[row["obis"]]["c"] = 1
          else:
            data[row["obis"]]["c"] = data[row["obis"]]["c"] + 1
      for k in data:
        del(data[k]["c"])
      return data
    except:
      self.__log.log(pyLOG.LogLvl.ERROR, "Could not extract data from database.\n{}".format(traceback.format_exc()))
      return None

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def getMeters(self):
    return self.__tab_meters

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def getUnits(self):
    return self.__tab_units

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def getObis(self):
    return self.__tab_obis

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def getLastTimestamp(self, meter=None, format=None):
    if ( None != meter ):
      try:
        self.__sql_cur.execute("SELECT * FROM v_{} ORDER BY timestamp DESC LIMIT 1;".format(meter))
        row = self.__sql_cur.fetchone()
        try   : ts = datetime.datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%S.%f")
        except: ts = None
      except:
        row = None
    else:
      try:
        self.__sql_cur.execute("SELECT * FROM m_TIMESTAMPS ORDER BY value DESC LIMIT 1;")
        row = self.__sql_cur.fetchone()
        try   : ts = datetime.datetime.strptime(row["value"], "%Y-%m-%dT%H:%M:%S.%f")
        except: ts = None
      except:
        row = None
    try:
      if   ( None != format and None != ts ): return ts.strftime(frmat)
      else                                  : return ts
    except:
      return None

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  meters    = property(getMeters)
  units     = property(getUnits)
  obis      = property(getObis)

########################################################################################################################

class HM_WebSrv_HTTPRequestHandler(http.server.BaseHTTPRequestHandler):
  """
  @brief   HM web server HTTP request handler for python http.server.
  """

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __init__(self, cfg):
    """
    @brief   Constructor.
    @param   cfg   A HM web server configuration.
    """
    self.__cfg = cfg
    self.__log = pyLOG.Log(self.__cfg["logref"])
    self.__sql = HM_WebSrv_Sql(self.__cfg)

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def do_GET(self):
    """
    @brief   Handler for GET requests.
    """
    pCFG = "hm.cfg"
    pDBF = self.__cfg["sqldb"].replace("\\", "/").strip(".").lstrip("/")

    if ( "images2" in self.path ): return

    if ( "/"+pCFG  == self.path ):
      f = open("hm.cfg", "rb")
      self.send_response(200)
      self.send_header('Content-type', 'text/plain')
      self.end_headers()
      self.wfile.write(f.read())
      f.close()
      return

    if ( "/"+pDBF  == self.path ):
      f = open("hm.sqlite", "rb")
      self.send_response(200)
      self.send_header('Content-type', 'application/octet-stream')
      self.end_headers()
      self.wfile.write(f.read())
      f.close()
      return

    self.__log.log_callinfo()

    pDTF   = None # date time from
    pDTU   = None # date time until
    pENP   = None # every nth point
    pMeter = []   # meter
    pObis  = []   # obis
    eError = []   # list of error messages

    self.__log.log(pyLOG.LogLvl.INFO, "Received request for url:{}".format(self.path))

    # parse url
    pURL = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
    self.__log.log(pyLOG.LogLvl.INFO, "Received request for parameters:\n{}".format(pprint.pformat(pURL)))

    # check url query parameters
    # - meter
    if ( "meter" not in pURL ):
      eError.append("URL query parameter 'meter' is not present.")
    else:
      if ( 1 != len(pURL["meter"]) ):
        eError.append("URL query parameter 'meter' is not a single value.")
      else:
        if   ( pURL["meter"][0] not in self.__sql.meters ): self.__sql.update()
        if   ( pURL["meter"][0] not in self.__sql.meters ): eError.append("URL query parameter 'meter' is not included in DB.")
        else                                           : pMeter = pURL["meter"][0]
    # - dtf
    if ( "dtf" not in pURL ):
      pDTF = datetime.datetime(1900, 1, 1)
      eError.append("URL query parameter 'dtf' is not present.")
    else:
      if ( 1 != len(pURL["dtf"]) ):
        eError.append("URL query parameter 'dtf' is not a single value.")
      else:
        try   : pDTF = datetime.datetime.strptime(pURL["dtf"][0], "%Y-%m-%d %H:%M")
        except: pDTF = datetime.datetime(1900, 1, 1); eError.append("URL query parameter 'dtf' is not of expected format.")
    # - dtu
    if ( "dtu" not in pURL ):
      pDTU = datetime.datetime(1900, 1, 2)
      eError.append("URL query parameter 'dtu' is not present.")
    else:
      if ( 1 != len(pURL["dtu"]) ):
        eError.append("URL query parameter 'dtu' is not a single value.")
      else:
        try   : pDTU = datetime.datetime.strptime(pURL["dtu"][0], "%Y-%m-%d %H:%M")
        except: pDTU = datetime.datetime(1900, 1, 2); eError.append("URL query parameter 'dtu' is not of expected format.")
    # - enp
    if ( "enp" not in pURL ):
      pENP = 300
      eError.append("URL query parameter 'enp' is not present.")
    else:
      if ( 1 != len(pURL["enp"]) ):
        eError.append("URL query parameter 'enp' is not a single value.")
      else:
        try   : pENP = int(pURL["enp"][0])
        except: pENP = 300; eError.append("URL query parameter 'enp' is not of expected data type 'integer'.")
    # - obis
    if ( "obis" not in pURL ):
      eError.append("URL query parameter 'obis' is not present.")
    else:
      if ( 0 == len(pURL["obis"]) ):
        eError.append("URL query parameter 'obis' is empty.")
      else:
        eObis = False
        for o in pURL["obis"]:
          try   :
            o = int(o)
          except:
            eError.append("URL query parameter 'obis = {}' is of expected data type 'integer'.".format(o)); eObis = True
          else:
            if ( o not in self.__sql.obis ): self.__sql.update()
            if ( o not in self.__sql.obis ): eError.append("URL query parameter 'obis = 0x{:X}' is not included in DB.".format(o)); eObis = True
        if ( False == eObis ): pObis = pURL["obis"]

    # log errors
    for e in eError:
      self.__log.log(pyLOG.LogLvl.ERROR, e)

    # switch date time values if necessary
    if pDTF > pDTU:
      pDTF, pDTU = pDTU, pDTF

    # send response status code
    self.send_response(200)

    # send headers
    self.send_header('Content-type','text/html')
    self.end_headers()

    # create html head
    if ( not eError ):
      html_head = """
  <head>
    <meta charset="utf-8"/>
    <style type="text/css">
      * {font: normal 10px Verdana, Arial, 'sans-serif' !important;}
    </style>
    <script src="https://www.rainforestnet.com/datetimepicker/javascript/datetimepicker_css.js"></script>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
  </head>
"""
    else:
      html_head = """
  <head>
    <meta charset="utf-8"/>
    <style type="text/css">* {font: normal 10px Verdana, Arial, 'sans-serif' !important;}</style>
    <script src="https://www.rainforestnet.com/datetimepicker/javascript/datetimepicker_css.js"></script>
  </head>
"""
    # create html plot
    if ( not eError ):
      try:
        data_plot = ""
        axis_plot = ""
        color     = 0x00FF00
        for i,(k,v) in enumerate(self.__sql.extract(pMeter, pDTF.isoformat(), pDTU.isoformat(), pENP, pObis).items()):
          random.seed(color)
          color = (random.randint(0,255)<<16) + (random.randint(0,255)<<8) + (random.randint(0,255))
          v["x"] = ["\""+str(i)+"\"" for i in v["x"]]
          v["y"] = [     str(i)      for i in v["y"]]
          nl     = {True:"\n", False:""}[i!=(len(pObis)-1)]
          yax_f  = {False:"yaxis     ", True:"yaxis{:<5}".format(i+1)}[bool(i)]
          yax_s  = {False:"", True:",\n{sp2}yaxis: 'y{}'".format(i+1, sp2=" "*6)}[bool(i)]
          axis_plot = axis_plot + "{sp1}{}: {{title: '{:X}', zeroline: false, titlefont: {{color: '#{col:X}'}}, tickfont: {{color: '#{col:X}'}}{}}},{}".format(yax_f, k, {True:", overlaying: 'y', position: {}, anchor: 'free'".format((len(pObis)*0.05)-(0.05*i)), False:""}[bool(i)], nl, col=color, sp1=" "*4)
          data_plot = data_plot + "{sp1}{{\n{sp2}x    : [{}],\n{sp2}y    : [{}],\n{sp2}type : 'scatter',\n{sp2}line : {{color: '#{col:X}', shape: 'vh'}}, \n{sp2}name : '{:X} [{}] ({} points)'{}\n{sp1}}},{}".format(",".join(v["x"]), ",".join(v["y"]), k, self.__sql.units[v["u"][0]]["dsc"], len(v["x"]), yax_s, nl, col=color, sp1=" "*4, sp2=" "*6)
      except:
        self.__log.log(pyLOG.LogLvl.ERROR, "Could not create html plot data.\n{}".format(traceback.format_exc()))
        data_plot = "{x:[0], y:[0], type:'scatter', name:'dummy'}"
      else:
        if ( not data_plot ):
          self.__log.log(pyLOG.LogLvl.ERROR, "No data to plot.")
          data_plot = "{x:[0], y:[0], type:'scatter', name:'dummy'}"

      try:
        html_plot = """
        <div id="id_{mtr}" style="width:90%;height:250px;"></div>
        <script>
          var selectorOptions = {{
              buttons: [{{
                  step: 'month',
                  stepmode: 'backward',
                  count: 1,
                  label: '1m'
              }}, {{
                  step: 'month',
                  stepmode: 'backward',
                  count: 6,
                  label: '6m'
              }}, {{
                  step: 'year',
                  stepmode: 'todate',
                  count: 1,
                  label: 'YTD'
              }}, {{
                  step: 'year',
                  stepmode: 'backward',
                  count: 1,
                  label: '1y'
              }}, {{
                  step: 'all',
              }}],
          }};
          var modebar= {{ modeBarButtonsToRemove: ['sendDataToCloud','toImage','zoom2d','pan2d','select2d','lasso2d','resetScale2d','hoverClosestCartesian','hoverCompareCartesian','zoom3d'] }};
          var fig_{mtr} = document.getElementById('id_{mtr}');
          var lay_{mtr} =
  {{
    title     : '{tit}',
    showlegend: true,
    margin    : {{t: 25}},
    xaxis     : {{domain: [{xax}, 1.0]}},
{yax}
  }};
          var dat_{mtr} =
  [
{dat}
  ];
          Plotly.plot(fig_{mtr}, dat_{mtr}, lay_{mtr}, modebar);
        </script>
    """.format(mtr=pMeter, xax=(len(pObis)*0.05), yax=axis_plot, dat=data_plot, tit="{} ({})".format(pMeter, self.__sql.meters[pMeter]["dsc"]))
      except:
        traceback.print_exc()
        html_plot = ""

    else:
      html_plot = "{tx}".format(tx="\n".join(["{sp}<p>{ms}</p>".format(sp=" "*4, ms=e) for e in eError]))

    # create html form
    html_form = """
    <form method="get">
      <input type='submit' value='Submit'/>
      <fieldset>
        <legend>
          Intervall
        </legend>
        <input type="text"   name="dtf" id="id_dtf" maxlength="25" size="25" value="{dtf}" required/> <img src="https://www.rainforestnet.com/datetimepicker/images2/cal.gif" onclick="javascript:NewCssCal('id_dtf', 'yyyyMMdd', 'arrow', 'true', '24', false, 'past')" style="cursor:pointer"/> <label for="id_dtf">Start date & time</label>
        <span style="display:inline-block; width:75;"></span>
        <input type="text"   name="dtu" id="id_dtu" maxlength="25" size="25" value="{dtu}" required/> <img src="https://www.rainforestnet.com/datetimepicker/images2/cal.gif" onclick="javascript:NewCssCal('id_dtu', 'yyyyMMdd', 'arrow', 'true', '24', false, 'past')" style="cursor:pointer"/> <label for="id_dtu">End date & time</label>
        <span style="display:inline-block; width:75;"></span>
        <input type="number" name="enp" id="id_enp" min="1" max="1000" value="{enp}" required> <label for="id_exp">only use every Nth point</label>
      </fieldset>
      <fieldset>
        <legend>
          Meters
        </legend>
{mtr}
      </fieldset>
      <fieldset>
        <legend>
          Indicators
        </legend>
{ind}
      </fieldset>
    </form>
""".format( dtf=pDTF.strftime("%Y-%m-%d %H:%M"),
            dtu=pDTU.strftime("%Y-%m-%d %H:%M"),
            enp=pENP,
            mtr="\n".join(["{sp}<input type=\"radio\"    name=\"meter\" id=\"id_{id}\" value=\"{id}\" {chk}><label for=\"id_{id}\">{id} ({ds})</label><br/>".format(         sp=" "*8, id=k, ds=v["dsc"],               chk={True:"checked", False:" "*7}[    k  in pMeter]) for k,v in sorted(self.__sql.meters.items())]),
            ind="\n".join(["{sp}<input type=\"checkbox\" name=\"obis\"  id=\"id_{id}\" value=\"{id}\" {chk}><label for=\"id_{id}\">{id:X}   [{un}]   ({ds})</label><br/>".format(sp=" "*8, id=k, ds=v["dsc"], un=v["unit"], chk={True:"checked", False:" "*7}[str(k) in pObis ]) for k,v in sorted(self.__sql.obis.items())  ]),
          )

    # create link
    html_link = """
    <a href="{cfg}">download configuration</a></br>
    <a href="{dbf}">download database</a>
    """.format(cfg=pCFG, dbf=pDBF)

    # create html
    html = "<html>\n" + html_head + "  <body>\n" + html_plot + html_form + html_link + "  </body>\n" + "</html>"

    self.wfile.write(bytes(html, "utf8"))
    return

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __call__(self, *args, **kwargs):
    """
    @brief   Workaround to pass an object of this class to socketserver.TCPServer.RequestHandlerClass via
             http.server.HTTPServer instead of the class itself
    """
    http.server.BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

########################################################################################################################

class HM_WebSrv(object):
  """
  @brief   HM data web server main class.
  """

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __init__(self, cfg):
    """
    @brief   Constructor.
    @param   cfg   A full HM configuration.
    """
    self.__cfg = cfg
    self.__log = pyLOG.Log(self.__cfg["general"]["logref"])
    self.__thd = threading.Thread(target=self.__run, args=())
    self.__srv = None

    self.__thd.start()

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def stop(self):
    """
    @brief   Trigger exiting the thread.
    """
    if ( None != self.__srv ): self.__srv.shutdown()

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def isalive(self):
    """
    @brief   Returns whether the server is running or not.
    """
    return ( None != self.__srv )

  #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  def __run(self):
    """
    @brief   Method holding the running web server in a separate thread.
    """
    self.__log.log(pyLOG.LogLvl.DEBUG, "Starting thread '{}'".format(self.__thd.name))
    self.__log.log_callinfo()
    try:
      self.__log.log(pyLOG.LogLvl.INFO, "configuring web server '{}/{}' started".format(self.__cfg["websrv"]["address"], self.__cfg["websrv"]["port"]))
      server_address = (self.__cfg["websrv"]["address"], self.__cfg["websrv"]["port"])
      self.__srv = http.server.HTTPServer(server_address, HM_WebSrv_HTTPRequestHandler(self.__cfg["websrv"]))
      self.__srv.socket = ssl.wrap_socket(self.__srv.socket,
                                          server_side=True,
                                          certfile=self.__cfg["websrv"]["cert"],
                                          ssl_version=ssl.PROTOCOL_TLSv1_2)
      self.__log.log(pyLOG.LogLvl.INFO, "configuring web server '{}/{}' done".format(self.__cfg["websrv"]["address"], self.__cfg["websrv"]["port"]))
    except:
      self.__log.log(pyLOG.LogLvl.INFO, "configuring web server '{}/{}' failed".format(self.__cfg["websrv"]["address"], self.__cfg["websrv"]["port"]))
      self.__log.log(pyLOG.LogLvl.ERROR, "{}".format(traceback.format_exc()))
      del(self.__srv)
      self.__srv = None
    else:
      self.__srv.serve_forever()
    finally:
      self.__log.log(pyLOG.LogLvl.DEBUG, "Exiting thread '{}'".format(self.__thd.name))
      del(self.__srv)
      self.__srv = None

########################################################################################################################

def signal_handler(signal, frame):
  """
  @brief   Application interrupt handler function.
  """
  global o_websrv
  o_websrv.stop()
  while ( True == o_websrv.isalive() ):
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
  o_websrv = HM_WebSrv(cfg)

  while ( True ):
    time.sleep(30)
