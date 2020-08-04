import os
from dotenv import load_dotenv
from flask import Flask, request, render_template, g
from twilio.twiml.messaging_response import MessagingResponse
from pprint import pprint   # makes payload look nicer to read
from twilio.rest import Client
from flask_googlemaps import GoogleMaps
from flask_googlemaps import Map
from geocoder import get_location
from image_classifier import get_tags
from skymap_db import SkyMapDB
import sqlite3

load_dotenv()

app = Flask(__name__)
GoogleMaps(app, key='AIzaSyB7VuAqmj1mzTxJPcHp73MVk4-TGAUhmwI')
client = Client()

sky_pics = {}
markers = []

DATABASE = 'data/skymap.db'

skydb = SkyMapDB(DATABASE)

def get_db():
	db = getattr(g, '_database', None)
	if db is None:
		db = g._database = sqlite3.connect(DATABASE)

	# connect to the database + save handle to global
	try:
		cur = db.cursor() # get cursor
		cur.execute("CREATE TABLE IF NOT EXISTS entries (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, latitude REAL, longitude REAL, region TEXT, country TEXT, photo_url TEXT)")
		db.commit()
		print("success")

	except Error as e:
		print("error!")
		print(e)
	return db

def respond(message):
    response = MessagingResponse()
    response.message(message)
    return str(response)


@app.route('/webhook', methods=['POST'])
def reply():
	db = get_db()
	cur = db.cursor()

	sender = request.form.get('From')
	media_msg = request.form.get('NumMedia')    # 1 if its a picture 
	message_latitude = request.values.get('Latitude')
	message_longitude = request.values.get('Longitude')

    # check if the user already sent in a pic. if they send something new, then update it
	if media_msg == '1' and sender in sky_pics:
		pic_url = request.form.get('MediaUrl0')  # URL of the person's media
		relevant_tags = get_tags(pic_url)

		print("The tags for your picture are : ", relevant_tags.keys())

		# check whether this is a picture of the sky
		if 'sky' in relevant_tags or 'weather' in relevant_tags:

			# they have not already submitted a picture
			if sky_pics.get(sender)[4] is None:
				sky_pics.get(sender)[4] = pic_url
				print("The sky_pics dictionary contains...")
				print(sky_pics)

				print(f'check whether {sender} exists in the database')
#				cur.execute("SELECT COUNT(*) FROM entries WHERE sender=?", (sender,))
#				count = cur.fetchone()[0]
#				if count > 0:
#					cur.execute("UPDATE entries SET photo_url=?", (pic_url,))
#					db.commit()
				
				if skydb.sender_exists(sender):
					skydb.update_photo(sender, pic_url)

				return respond(f'Sweet pic of the sky! Uploaded it to the map. Check it out at http://60f884add264.ngrok.io')
			
			# they're replacing a prior picture
			else:
				sky_pics.get(sender)[4] = pic_url # replace old picture with this one
				print("The sky_pics dictionary contains...")
				print(sky_pics)

#				print(f'check whether {sender} exists in the database')
#				cur.execute("SELECT COUNT(*) FROM entries WHERE sender=?", (sender,))
#				count = cur.fetchone()[0]
#				if count > 0:
#					cur.execute("UPDATE entries SET photo_url=?", (pic_url,))
#					db.commit()

				if skydb.photo_exists(sender):
					skydb.update_photo(sender, pic_url)

				return respond(f'Ok cool, it\'s fine to change your mind! We\'ll use this sky pic instead your previous one')
		
		# doesn't look like a pic of the sky
		else:
			pic_tags = list(relevant_tags.keys())
			return respond(f'Hmm, that doesn\'t look like the sky.\n\nLooks like your picture includes {pic_tags}.\n\nTry again?')

	# they've sent their location
	elif message_latitude is not None and message_longitude is not None:
		location = get_location(message_latitude, message_longitude)

		sky_pics[sender] = [None] * 5
		sky_pics.get(sender)[0] = message_latitude
		sky_pics.get(sender)[1] = message_longitude
		sky_pics.get(sender)[2] = location[0]
		sky_pics.get(sender)[3] = location[1]

		skydb.add_entry(sender, message_latitude, message_longitude, location[0], location[1])
		return respond(f'Cool, hope you\'re enjoying life in {location[0]} right now! Want to send us a pic of the sky there?')


	# this isn't either a picture or a location - prompt them to send one of those
	else:
		return respond(f'Hi there! Send us your location through whatsapp to get started.')


@app.route("/")
def mapview():
	db = get_db()
	cur = db.cursor()
#	for entry in sky_pics:
	cur.execute("SELECT latitude, longitude, photo_url FROM entries")
	rows = cur.fetchall()
	for row in rows:
		if row[2] is None:
        #if sky_pics.get(entry)[4] is None:
			url_entry_pic = 'https://s3-external-1.amazonaws.com/media.twiliocdn.com/ACa2dea70cb125daf20c4ac433be77eda4/d7a07ccac2cf9321e82559c82beff7ed'       # random filler pic
			sky_pics.get(entry)[4] = url_entry_pic
		else:
			url_entry_pic = row[2]
#        markers.append({
#            'icon': 'http://maps.google.com/mapfiles/ms/icons/green-dot.png',
#            'lat': sky_pics.get(entry)[0], 
#            'lng': sky_pics.get(entry)[1],
#            'infobox': '<div id="bodyContent">' +
#                '<img src="' + sky_pics.get(entry)[4] + '" alt = "sky" style="width:175px;height:220px;"></img>' + '</div>' 
#        })
		markers.append({
			'icon': 'http://maps.google.com/mapfiles/ms/icons/green-dot.png',
			'lat': row[0], 
			'lng': row[1],
			'infobox': '<div id="bodyContent">' +
                '<img src="' + url_entry_pic + '" alt = "sky" style="width:175px;height:220px;"></img>' + '</div>' 
		})
	mymap = Map(
        identifier="sndmap",
        style=(
            "height:100%;"
            "width:100%;"
            "top:0;"
            "position:absolute;"
            "z-index:200;"
            "zoom: -9999999;"
        ),
        # these coordinates re-center the map
        lat=37.805355,
        lng=-122.322618,
        markers = markers,
	)
	return render_template('index.html', mymap=mymap)
 
@app.teardown_appcontext
def close_connection(exception):
	db = getattr(g, '_database', None)
	if db is not None:
		db.close()