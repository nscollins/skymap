import os
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta
from flask import Flask, request, render_template, g
from twilio.twiml.messaging_response import MessagingResponse
from pprint import pprint   # makes payload look nicer to read
from twilio.rest import Client
from geojson import FeatureCollection, Feature, Point, dumps
from geocoder import get_location
from image_classifier import get_tags
import firebase_admin
from firebase_admin import credentials, db

load_dotenv()

# initialize the flask app
app = Flask(__name__,
            static_folder='static',
            static_url_path='/static',
            template_folder='templates')

# initialize the Twilio client interface
client = Client()

# initialize the firebase realtime database
cred = credentials.Certificate({
	'type': os.getenv('FIREBASE_TYPE'),
	'private_key': os.getenv('FIREBASE_PRIVATE_KEY').replace("\\n", "\n"),
	'client_email': os.getenv('FIREBASE_CLIENT_EMAIL'),
	'token_uri': os.getenv('FIREBASE_TOKEN_URI')
})
firebase_admin.initialize_app(cred, {
	'databaseURL': 'https://sky-map-284203.firebaseio.com/'
})

#cred = credentials.Certificate("cred/skymap-firebase-cred.json")
#firebase_admin.initialize_app(cred, {
#	'databaseURL': 'https://sky-map-284203.firebaseio.com/'
#})

def respond(message):
    response = MessagingResponse()
    response.message(message)
    return str(response)


@app.route('/webhook', methods=['POST'])
def reply():
	ref = db.reference('/')

	sender = request.form.get('From')
	media_msg = request.form.get('NumMedia')    # 1 if its a picture 
	message_latitude = request.values.get('Latitude')
	message_longitude = request.values.get('Longitude')

	sender_ref = ref.child(sender)

    # check if the user already sent in a pic. if they send something new, then update it
	entry = sender_ref.get()

	if media_msg == '1' and entry is not None:
		pic_url = request.form.get('MediaUrl0')  # URL of the person's media
		relevant_tags = get_tags(pic_url)
		print("The tags for your picture are : ", relevant_tags.keys())

		# check whether this is a picture of the sky and save to db if so
		if 'sky' in relevant_tags or 'weather' in relevant_tags:			
			# send the right message depending on whether there was a picture before

			already_existed = 'photo_url' in entry
			sender_ref.update({
				'photo_url': pic_url,
				'timestamp': time.time()
			})		

			if already_existed:
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
		if entry is not None:
			sender_ref.update({
				'longitude': float(message_longitude),
				'latitude': float(message_latitude),
				'timestamp': time.time()				
			})
			print("I updated the entry")
		else:
			ref.update({
				sender : {
					'longitude': float(message_longitude),
					'latitude': float(message_latitude),
					'timestamp': time.time()
				}
			})
			print("I added a new entry")
		return respond(f'Cool, hope you\'re enjoying life in {location[0]} right now! Want to send us a pic of the sky there?')

	# this isn't either a picture or a location - prompt them to send one of those
	else:
		if entry is not None:
			days_ago = (datetime.now() - datetime.fromtimestamp(entry['timestamp'])).days

			if days_ago == 0:
				return respond(f"Hey {entry['name']}! Didn't we just chat? Have a new location or picture to send me?")
			else:
				return respond(f"I've missed you, {entry['name']}! It's been {days_ago} days since we last talked. Send a new location if you're somewhere else and a fresh picture of the sky.")
		else:
			return respond(f'Hi there! Send us your location through whatsapp to get started.')


@app.route("/")
def mapview():
	ref = db.reference('/')
	entries = ref.get()

	collection = []		# list to store geojson featurecollection

	for sender in entries:
		entry = entries[sender]

		if 'photo_url' in entry:
			url_entry_pic = entry['photo_url']
		else:
			url_entry_pic = 'https://s3-external-1.amazonaws.com/media.twiliocdn.com/ACa2dea70cb125daf20c4ac433be77eda4/d7a07ccac2cf9321e82559c82beff7ed'       # random filler pic

		# construct the geojson feature for this entry
		img_tag = '<img src=\"' + url_entry_pic + '\"">'
		props = {
			'description': "",
			'photo': img_tag
		}
		cur_feature = Feature(geometry=Point((entry['longitude'], entry['latitude'])), properties=props) # LongLat
		collection.append(cur_feature)

	feature_collection = FeatureCollection(collection)
	# geojson dumps to convert FeatureCollection object into string
	mapdata = dumps(feature_collection, sort_keys=True, indent=4)

	return render_template('index.html', mapdata=mapdata)
