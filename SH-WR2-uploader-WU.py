#!/usr/bin/env python3
# Weather Underground Upload Script for WeatherSense SwitchDoc Labs Weather in combination with the SenseHat Sensors
# --------------------------------------------------------------------------------------------------------------------------------------------------------------
# Adapted from Switch Doc Labs readWeatherSensors.py script for testing the WeatherRack2
# Adapted from John Wargo SH to WU script https://github.com/johnwargo/pi_weather_station/blob/master/weather_station.py
# --------------------------------------------------------------------------------------------------------------------------------------------------------------
import sys
import requests
from subprocess import PIPE, Popen, STDOUT
from threading  import Thread
import json
import datetime as dt
from datetime import datetime
import pytz
from pytz import timezone
import time
import logging
import math
import urllib

from sense_hat import SenseHat

from config import Config

try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode

# -------------------------------------------------------------------------------------------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------------------------------------------------------------------------------------------

DEBUG_MODE = True
# specifies how often to measure values from the Sense HAT (in minutes)
PWS_INTERVAL = 2  # minutes
# Set to False when testing the code and/or hardware
# Set to True to enable upload of weather data to Weather Underground
WEATHER_UPLOAD = True


# constants used to display an up and down arrows plus bars
# modified from https://www.raspberrypi.org/learning/getting-started-with-the-sense-hat/worksheet/
# set up the colours (blue, red, empty)
b = [0, 0, 255]  # blue
r = [255, 0, 0]  # red
g = [0,128,0]    # green
y = [255,255,0]  # yellow
e = [0, 0, 0]    # empty

# create images for up and down arrows
arrow_up = [
    e, e, e, r, r, e, e, e,
    e, e, r, r, r, r, e, e,
    e, r, e, r, r, e, r, e,
    r, e, e, r, r, e, e, r,
    e, e, e, r, r, e, e, e,
    e, e, e, r, r, e, e, e,
    e, e, e, r, r, e, e, e,
    e, e, e, r, r, e, e, e
]
arrow_down = [
    e, e, e, b, b, e, e, e,
    e, e, e, b, b, e, e, e,
    e, e, e, b, b, e, e, e,
    e, e, e, b, b, e, e, e,
    b, e, e, b, b, e, e, b,
    e, b, e, b, b, e, b, e,
    e, e, b, b, b, b, e, e,
    e, e, e, b, b, e, e, e
]
bars = [
    e, e, e, e, e, e, e, e,
    e, e, e, e, e, e, e, e,
    r, r, r, r, r, r, r, r,
    r, r, r, r, r, r, r, r,
    b, b, b, b, b, b, b, b,
    b, b, b, b, b, b, b, b,
    e, e, e, e, e, e, e, e,
    e, e, e, e, e, e, e, e
]
plus = [
    e, e, e, g, g, e, e, e,
    e, e, e, g, g, e, e, e,
    e, e, e, g, g, e, e, e,
    g, g, g, g, g, g, g, g,
    g, g, g, g, g, g, g, g,
    e, e, e, g, g, e, e, e,
    e, e, e, g, g, e, e, e,
    e, e, e, g, g, e, e, e,
]

# Initialize some global variables
# last_temp = 0
wu_station_id = ''
wu_station_key = ''
pws_station_id = ''
pws_station_key = ''
sense = None
shMsg = ''
failct = 0
goodct = 0

# initialize the lastMinute variable to the current time to start
last_minute = dt.datetime.now().minute
# on init, just use the previous minute as lastMinute
last_minute -= 1
if last_minute == 0:
    last_minute = 59
    logging.debug('Last Minute: {}'.format(last_minute))

# Setup the basic console logger
format_str = '%(asctime)s %(levelname)s %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'
logging.basicConfig(format=format_str, level=logging.INFO, datefmt=date_format)
# When debugging, uncomment the following two lines
# logger = logging.getLogger()
# logger.setLevel(logging.DEBUG)

# -------------------------------------------------------------------------------------------------------------------------------------------------------------
# URL Formation and WU initialization 
# -------------------------------------------------------------------------------------------------------------------------------------------------------------

#  Read Weather Underground Configuration
logging.info('Initializing Weather Underground configuration')
wu_station_id = Config.WU_STATION_ID
wu_station_key = Config.WU_STATION_KEY
if (wu_station_id == "") or (wu_station_key == ""):
    logging.error('Missing values from the Weather Underground configuration file')
    sys.exit(1)

#  Read PWSweather.com  Configuration
logging.info('Initializing PWSweather.com configuration')
pws_station_id = Config.PWS_STATION_ID
pws_station_key = Config.PWS_STATION_KEY
if (pws_station_id == "") or (pws_station_key == ""):
    logging.error('Missing values from the PWS Weather configuration file')
    sys.exit(1)

# we made it this far, so it must have worked...
logging.info('Successfully read Weather Underground configuration')
logging.info('WU Station ID: {}'.format(wu_station_id))
logging.debug('Station key: {}'.format(wu_station_key))
logging.info('Successfully read PWSweather configuration')
logging.info('Station ID: {}'.format(pws_station_id))
logging.debug('Station key: {}'.format(pws_station_key))

date_str = "&dateutc=now"  #Default date stamp for weather services


# Weather Underground URL formation --------
# Create a string to hold the first part of the URL
# Standard upload
#WUurl = "https://weatherstation.wunderground.com/weatherstation/updateweatherstation.php?"
#WUaction_str = "&action=updateraw"

# Rapid fire server
WUurl = "https://rtupdate.wunderground.com/weatherstation/updateweatherstation.php?"
WUaction_str = "&realtime=1&rtfreq=16"

WUcreds = "ID=" + wu_station_id + "&PASSWORD="+ wu_station_key


# PWS weather URL formation --------
# Create a string to hold the first part of the URL
PWSurl = "https://pwsweather.com/weatherstation/updateweatherstation.php?"
PWSaction_str = "&action=updateraw"

PWScreds = "ID=" + pws_station_id + "&PASSWORD="+ pws_station_key

# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
# initialize the Sense HAT object
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
try:
    logging.info('Initializing the Sense HAT client')
    sense = SenseHat()
    sense.set_rotation(90)
    # then write some text to the Sense HAT
    sense.show_message('Power Up', text_colour=r, back_colour=[0, 0, 0])
    # clear the screen
    sense.clear()
except:
    logging.info('Unable to initialize the Sense HAT library')
    logging.error('Exception type: {}'.format(type(e)))
    logging.error('Error: {}'.format(sys.exc_info()[0]))
    print (sys.stdout)
    sys.exit(1)

logging.info('Initialization complete!')

# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
# 146 = FT-020T WeatherRack2, #147 = F016TH SDL Temperature/Humidity Sensor
logging.info('Starting Wireless Read')
#cmd = [ '/usr/local/bin/rtl_433', '-vv',  '-q', '-F', 'json', '-R', '146', '-R', '147']
cmd = [ '/usr/local/bin/rtl_433', '-q', '-F', 'json', '-R', '146', '-R', '147']

# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
#   A few helper functions...

def nowStr():
    return( datetime.datetime.now().strftime( '%Y-%m-%d %H:%M:%S'))

#   We're using a queue to capture output as it occurs
try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty  # python 3.x
ON_POSIX = 'posix' in sys.builtin_module_names

def enqueue_output(src, out, queue):
    for line in iter(out.readline, b''):
        queue.put(( src, line))
        logging.info('Queue Size {}'.format(queue.qsize()))
    out.close()

def get_dew_point_c(t_air_c, rel_humidity):
    """Compute the dew point in degrees Celsius

    :param t_air_c: current ambient temperature in degrees Celsius
    :type t_air_c: float
    :param rel_humidity: relative humidity in %
    :type rel_humidity: float
    :return: the dew point in degrees Celsius
    :rtype: float
    """
    A = 17.27
    B = 237.7
    alpha = ((A * t_air_c) / (B + t_air_c)) + math.log(rel_humidity/100.0)
    return (B * alpha) / (A - alpha)

#   Create our sub-process...
#   Note that we need to either ignore output from STDERR or merge it with STDOUT due to a limitation/bug somewhere under the covers of "subprocess"
#   > this took awhile to figure out a reliable approach for handling it...
p = Popen( cmd, stdout=PIPE, stderr=STDOUT, bufsize=1, close_fds=ON_POSIX)
q = Queue()

t = Thread(target=enqueue_output, args=('stdout', p.stdout, q))

t.daemon = True # thread dies with the program
t.start()

# ---------------------------------------------------------------------------------------------------------------------------------------------------------------

pulse = 0
while True:
    #   Other processing can occur here as needed...
    logging.info('Looking for WR2 data')

    try:
        src, line = q.get(timeout = 1)
        #print(line.decode())
    except Empty:
        pulse += 1
    else: # got line
        pulse -= 1
        sLine = line.decode()
        #print(sLine)
        #   See if the data is something we need to act on...
        if (( sLine.find('F007TH') != -1) or ( sLine.find('F016TH') != -1)):
            logging.info('WeatherSense Indoor T/H F016TH Found')
            logging.info('raw data: ' + sLine)
            # Variable Processing from JSON output from Indoor T/H unit for WU upload
            logging.info('Variable processing of Indoor T/H raw data.')
            raw_data = json.loads(sLine)
            indhumidity_str = "{0:.0f}".format(raw_data['humidity'])
            indtemp_str =  "{0:.1f}".format(raw_data['temperature_F'])
            logging.info('Indoor Temp: ' + indtemp_str)
            logging.info('Indoor Humidity: ' + indhumidity_str)
            # Send the local data to the SenseHat
            shMsg= indtemp_str + "F " + " " + indhumidity_str + "%"
            sense.show_message(shMsg, text_colour=[255, 255, 0], back_colour=[0, 51, 0])
            # clear the screen
            sense.clear()
        if (( sLine.find('FT0300') != -1) or ( sLine.find('FT020T') != -1)):
            logging.info('WeatherSense WeatherRack2 FT020T found')
            logging.info('raw data: ' + sLine)
	    # Variable Processing from SH unit for WU upload
            logging.info('Variable processing of SH raw data.')
            baro_str = "{0:.2f}".format (sense.get_pressure() * 0.0295300)
            # Variable Processing from JSON output from WR2 unit for WU upload
            logging.info('Variable processing of WR2 raw data.')
            raw_data = json.loads(sLine)
            time_stamp = (raw_data['time'])

            # Convert Timezone to UTC using timestamp from WR2
            # Adjust values below to match your timezone etc
            # If you are using date=now for your upload to WU comment out this section
            utc = timezone('UTC')
            central = timezone('US/Central')
            published_time = datetime.strptime(time_stamp, '%Y-%m-%d %H:%M:%S')
            published_cst = published_time.replace(tzinfo=central)
            published_gmt = published_time.astimezone(utc)
            actual_time_published = published_gmt.strftime('%Y-%m-%d %H:%M:%S')
            # URL Encode timestamp
            time_str = (urllib.parse.quote(actual_time_published, safe=''))
            # Format process weather variables into strings for  upload
            humidity_str = "{0:.0f}".format(raw_data['humidity'])
            humpct = (raw_data['humidity'])
            tempf = ((raw_data['temperature']-400)/10.0)
            tempc = ((tempf-32.0)*5.0/9.0)
            temp_str =  "{0:.1f}".format((raw_data['temperature']-400.0)/10.0)
            # Dew Point Calcs
            dewptc = get_dew_point_c(tempc, humpct)
            dewpt_str = "{0:.1f}".format((dewptc *9.0/5.0)+32.0)
            winddir_str = "{0:.0f}".format(raw_data['winddirection'])
            avewind_str = "{0:.2f}".format(raw_data['avewindspeed'] * 0.2237)
            gustwind_str = "{0:.2f}".format(raw_data['gustwindspeed'] * 0.2237)
            cumrain_str = "{0:.2f}".format(raw_data['cumulativerain'] * 0.003937)
            uv_str = "{0:.1f}".format(raw_data['uv'] * 0.1)
            light_str = "{0:.0f}".format(raw_data['light'])
            # Send the temp / humidity data to the SenseHat
            shMsg= temp_str +  "F " + " " + humidity_str + "%"
            sense.show_message(shMsg, text_colour=[255, 255, 0], back_colour=[0, 0, 102])
            # clear the screen
            sense.clear()

            # Form URL into WU format and Send
            wur= requests.get(
                WUurl +
                WUcreds +
                "&dateutc=" + time_str + #Formatted time stamp from WR2, comment line out to use "now" option for WU
                #date_str +  #Use as a replacement for actual time stamp uncomment to use "now" function of WU 
		"&tempf=" + temp_str +
                "&humidity=" + humidity_str +
                "&dewptf=" + dewpt_str +
                "&winddir=" + winddir_str  +
                "&windspeedmph=" + avewind_str +
                "&windgustmph=" + gustwind_str +
                "&dailyrainin=" + cumrain_str +
                "&uv=" + uv_str +
                "&baromin=" + baro_str +
                "&softwaretype=" + "Pi3-SH-WR2-Updater" +
                WUaction_str)

            # Check upload time against interval
            # get the current minute
            current_minute = dt.datetime.now().minute
            logging.info('Current minute: {}'.format(current_minute))
            # is it the same minute as the last time we checked?
            # this will always be true the first time through this loop
            if current_minute != last_minute:
                # reset last_minute to the current_minute
                last_minute = current_minute
                # is minute zero, or divisible by 10?
                # we're only going to use measurements every MEASUREMENT_INTERVAL minutes
                if (current_minute == 0) or ((current_minute % PWS_INTERVAL) == 0):
                    # get the reading timestamp
                    now = dt.datetime.now()
                    logging.info("%d minute mark (%d @ %s)" % (PWS_INTERVAL, current_minute, str(now)))
                    # Form URL into PWS format and Send
                    pwsr= requests.get(
                        PWSurl +
                        PWScreds +
                        "&dateutc=" + time_str + #Formatted time stamp from WR2, comment line out to use "now" option for WU
                        #date_str +  #Use as a replacement for actual time stamp uncomment to use "now" function of WU
                        "&tempf=" + temp_str +
                        "&humidity=" + humidity_str +
                        "&dewptf=" + dewpt_str +
                        "&winddir=" + winddir_str  +
                        "&windspeedmph=" + avewind_str +
                        "&windgustmph=" + gustwind_str +
                        "&dailyrainin=" + cumrain_str +
                        "&uv=" + uv_str +
                        "&baromin=" + baro_str +
                        "&softwaretype=" + "Pi3-SH-WR2-Updater" +
                        PWSaction_str)
                    # Check PWS Feed Status
                    logging.info('PWS Received ' + str(pwsr.status_code) + '++++++++++++++++++++++++++++++++++')
            else:
                logging.info('Skipping PWSweather.com upload-------------------------------------')
            # Show a copy of what you formed up and are uploading in HRF
            logging.info('WU URL ' + WUurl)
            logging.info('WU Creds ' + WUcreds)
            logging.info('Time Stamp ' + time_str)
            logging.info('Outdoor Temp ' + temp_str)
            logging.info('Humidity ' + humidity_str)
            logging.info('Dew Point ' + dewpt_str)
            logging.info('Wind Direction ' + winddir_str)
            logging.info('Wind Speed Ave ' + avewind_str)
            logging.info('Wind Speed Gust ' + gustwind_str)
            logging.info('Rain total ' + cumrain_str)
            logging.info('UV ' + uv_str)
            logging.info('Barometer' +baro_str)
            logging.info('Software Pi3-SH-WR2-Updater')
            logging.info('WU Action ' + WUaction_str)

            # Check WU Feed Status
            logging.info('WU Received ' + str(wur.status_code) + ' ' + str(wur.text))
            # display  green cross for success or a red arrow for fail
            if (wur.status_code == 200):
                sense.set_pixels(plus)
                time.sleep(1)
                sense.clear()
                # increase good upload count
                goodct += 1
                logging.info('Good Upload Count: {}'.format(goodct) + ' Failed Upload Count: {}'.format(failct))
            else:
                sense.set_pixels(arrow_up)
                time.sleep(1)
                sense.clear()
                # increase fail upload count 
                failct += 1
                logging.info('Good Upload Count: {}'.format(goodct) + ' Failed Upload Count: {}'.format(failct))

    #logging.info('@Interval Pulse Count: {}'.format(pulse))
    #logging.info('Queue Size: {}'.format(queue.qsize()))
        sys.stdout.flush()
