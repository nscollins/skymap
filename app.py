import os
from dotenv import load_dotenv
from flask import Flask, request, render_template, g
from twilio.twiml.messaging_response import MessagingResponse
from pprint import pprint   # makes payload look nicer to read
from twilio.rest import Client
from flask_googlemaps import GoogleMaps
from flask_googlemaps import Map
from geojson import FeatureCollection, Feature, Point, dumps
from geocoder import get_location
from image_classifier import get_tags
from skymap_db import SkyMapDB

load_dotenv()

app = Flask(__name__)
GoogleMaps(app, key='AIzaSyB7VuAqmj1mzTxJPcHp73MVk4-TGAUhmwI')
client = Client()

DATABASE = 'data/skymap.db'
skydb = SkyMapDB(DATABASE)

markers = []

def respond(message):
    response = MessagingResponse()
    response.message(message)
    return str(response)


@app.route('/webhook', methods=['POST'])
def reply():
	skydb.connect()

	sender = request.form.get('From')
	media_msg = request.form.get('NumMedia')    # 1 if its a picture 
	message_latitude = request.values.get('Latitude')
	message_longitude = request.values.get('Longitude')

    # check if the user already sent in a pic. if they send something new, then update it
	if media_msg == '1' and skydb.sender_exists(sender):
		pic_url = request.form.get('MediaUrl0')  # URL of the person's media
		relevant_tags = get_tags(pic_url)

		print("The tags for your picture are : ", relevant_tags.keys())

		# check whether this is a picture of the sky and save to db if so
		if 'sky' in relevant_tags or 'weather' in relevant_tags:
			skydb.update_photo(sender, pic_url)
			# send the right message depending on whether there was a picture before
			if skydb.photo_exists(sender):
				return respond(f'Ok cool, it\'s fine to change your mind! We\'ll use this sky pic instead of your previous one. Updated on https://sky-map.herokuapp.com/')			
			else:
				return respond(f'Sweet pic of the sky! Uploaded it to the map. Check it out at https://sky-map.herokuapp.com/')
		
		# doesn't look like a pic of the sky
		else:
			pic_tags = list(relevant_tags.keys())
			return respond(f'Hmm, that doesn\'t look like the sky.\n\nLooks like your picture includes {pic_tags}.\n\nTry again?')

	# they've sent their location
	elif message_latitude is not None and message_longitude is not None:
		location = get_location(message_latitude, message_longitude)
		skydb.add_entry(sender, message_latitude, message_longitude, location[0], location[1])
		return respond(f'Cool, hope you\'re enjoying life in {location[0]} right now! Want to send us a pic of the sky there?')

	# this isn't either a picture or a location - prompt them to send one of those
	else:
		if skydb.sender_exists(sender):
			days_ago = skydb.last_interaction(sender)
			if days_ago == 0:
				return respond(f"Well, hello again! Didn't we just chat? Have a new location or picture to send me?")
			else:
				return respond(f"I've missed you! It's been {days_ago} days since we last talked. Send a new location if you're somewhere else and a fresh picture of the sky.")
		else:
			return respond(f'Hi there! Send us your location through whatsapp to get started.')

@app.route("/")
def mapview():
	skydb.connect()
	rows = skydb.get_map_entries()	# list of sets of latitude, longitude, photo_url
	collection = []		# list to store geojson featurecollection

	for row in rows:
		if row[2] is None:
			url_entry_pic = 'https://s3-external-1.amazonaws.com/media.twiliocdn.com/ACa2dea70cb125daf20c4ac433be77eda4/d7a07ccac2cf9321e82559c82beff7ed'       # random filler pic
		else:
			url_entry_pic = row[2]

		# construct the geojson feature for this entry
		img_tag = '<img src=\"' + url_entry_pic + '\"">'
		props = {
			'description': "",
			'photo': img_tag
		}
		cur_feature = Feature(geometry=Point((row[1], row[0])), properties=props) # LongLat
		collection.append(cur_feature)

	feature_collection = FeatureCollection(collection)
	# geojson dumps to convert FeatureCollection object into string
	mapdata = dumps(feature_collection, sort_keys=True, indent=4)

	return render_template('index.html', mapdata=mapdata)
 
@app.teardown_appcontext
def close_connection(exception):
	skydb.disconnect()
