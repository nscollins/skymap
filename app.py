import os
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta
from flask import Flask, request, render_template, make_response, g
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

'''
# current state key maps to next state value
state = {
	'greeting': 'name',
	'name': 'location',
	'location': 'photo',
	'photo': 'complete'
}
'''

map_url = 'http://sky-map.herokupapp.com'

'''
# dictionary of messages to send in different states
messages = {
	'greeting': {
		'initial': 'Hi there! It\'s nice to meet you.',
		'repeat': 'I\'ve missed you, {entry['name']}! I\'s been {days_ago} days since we last talked.'
	},
	'name': {
		'initial': 'I\'m a robot. I don\'t really have a name, but I bet you do. What is it? Just first name, we can be friends.',
		'repeat': 'Is that really your name? Seems hard to say. Tell me your first name again?',
		'confirm': 'That\'s a pretty name, {entry['name']}.'
	},
	'location': {
		'initial': 'Where in the world are you? Send me your location using the "+" on the bottom left to get started.',
		'repeat': 'Ok, let\'s try this. Tap the "+" on the bottom left and choose Current Location from the list.',
		'confirm': 'Cool, hope you\'re enjoying life in {location[0]} right now!'
	},
	'photo': {
		'initial': 'Want to send me a pic of the sky there?',
		'repeat': 'Hmm, that doesn\'t look like the sky.\n\nLooks like your picture includes {pic_tags}.\n\nTry again?',
		'confirm': 'Sweet pic of the sky! Uploaded it to the map. Check it out at {map_url}'
	},
	'complete' : {
		'initial': 'It\'s been a while since we\'ve talked. Have a new location or photo for me?',
		'repeat': 'You keep coming to say hi. I like it. Want to update your location or photo?',
		'confirm': 'Cool, I\'ll update that one the map. Check it out at {map_url}'
	},
	'confused': 'I didn\'t quite get that.'
}
'''

def respond(message, askedname=0):
    twml = MessagingResponse()
    twml.message(message)
    resp = make_response(str(twml))

    # include a cookie that marks askedname to 1 for 2 hours if we just asked the name
    expires = datetime.utcnow() + timedelta(hours=2)
    resp.set_cookie('askedname',value=str(askedname),expires=expires.strftime('%a, %d %b %Y %H:%M:%S GMT'))

    return resp	


def remaining_info(db_entry_ref, prefix):
	entry = db_entry_ref.get()		# pull the latest data from firebase

	if 'name' not in entry:
		# ask for the name
		return respond(f'{prefix}\n\nWhat\'s your name again?', 1)
	elif 'latitude' not in entry or 'longitude' not in entry:
		# ask for location
		return respond(f'{prefix}\n\nWhere in the world are you? Send me your location using the "+" to the left of the message box.')
	elif 'photo_url' not in entry:
		# ask for the photo
		return respond(f'{prefix}\n\nWant to send me a pic of the sky there?')
	else:
		# direct them to check out skymap
		return respond(f'{prefix}\n\nCheck out {map_url}')


@app.route('/webhook', methods=['POST'])
def reply():
	ref = db.reference('/')

	# data from the Twilio/whatsapp message
	sender = request.form.get('From')
	message_body = request.form.get('Body')					# text of the message
	media_msg = request.form.get('NumMedia')				# is this a media message?
	media_type = request.form.get('MediaContentType0')		# if so, what type?
	message_latitude = request.values.get('Latitude')
	message_longitude = request.values.get('Longitude')
	askedname = int(request.cookies.get('askedname',0))

	# firebase reference to this sender's data, if it exists
	sender_ref = ref.child(sender)
	entry = sender_ref.get()

	# first time we're seeing this person
	if entry is None:
		if message_latitude is not None and message_longitude is not None:
			ref.update({
				sender : {
					'longitude': float(message_longitude),
					'latitude': float(message_latitude),
					'timestamp': time.time(),
				}
			})
		else:
			ref.update({
				sender : {
					'timestamp': time.time(),
				}
			})
		return respond(f'Hi there! It\'s nice to meet you. I\'m a robot. I don\'t really have a name, but I bet you do. What is it? Just first name, we can be friends.', 1)

	# we have this number in our database already
	else:
		# photo message
		if media_msg == '1':
			if media_type == 'image/jpeg':
				pic_url = request.form.get('MediaUrl0')  # URL of the person's media
				relevant_tags = get_tags(pic_url)
				print("The tags for your picture are : ", relevant_tags.keys())

				# check whether this is a picture of the sky and save to db if so
				if 'sky' in relevant_tags or 'weather' in relevant_tags:			
					# send the right message depending on whether there was a picture before

					already_existed = 'photo_url' in entry
					sender_ref.update({
						'photo_url': pic_url,
						'timestamp': time.time(),
					})		

					if already_existed:
						prefix = f'Ok cool, it\'s fine to change your mind! We\'ll use this sky pic instead of your previous one.'			
						#respond(f'Ok cool, it\'s fine to change your mind! We\'ll use this sky pic instead of your previous one. Updated on https://sky-map.herokuapp.com/')			
					else:
						prefix = f'Sweet pic of the sky! Uploaded it to the map.'			
						#respond(f'Sweet pic of the sky! Uploaded it to the map. Check it out at https://sky-map.herokuapp.com/')
					return remaining_info(sender_ref, prefix)

				# doesn't look like a pic of the sky
				else:
					pic_tags = ", ".join(list(relevant_tags.keys()))
					return respond(f'Hmm, that doesn\'t look like the sky.\n\nLooks like your picture includes: {pic_tags}.\n\nTry again?')
			# holler if it's a non-image media type
			else:
				return respond(f'Sorry, I don\'t understand that kind of media yet.')

		# correctly formed location message
		elif message_latitude is not None and message_longitude is not None:
			location = get_location(message_latitude, message_longitude)
			sender_ref.update({
				'longitude': float(message_longitude),
				'latitude': float(message_latitude),
				'timestamp': time.time()				
			})
			# respond(f'Cool, hope you\'re enjoying life in {location[0]} right now!')
			return remaining_info(sender_ref, f'Cool, hope you\'re enjoying life in {location[0]} right now!')

		# this might be the name response
		elif 'name' not in entry and askedname == 1 and message_body != '':
			sender_ref.update({
				'name': message_body,
				'timestamp': time.time()				
			})
			# respond(f'Nice to get to know you, {message_body}!')
			return remaining_info(sender_ref, f'Nice to get to know you, {message_body}!')	

		# any other kind of message, probably text
		else:
			days_ago = (datetime.now() - datetime.fromtimestamp(entry['timestamp'])).days
			name_greeting = ''
			if 'name' in entry:
				name_greeting = ', ' + entry['name']

			if days_ago == 0:
				return respond(f"Hey{name_greeting}! Didn't we just chat? Have a new location or picture to send me?")
			else:
				return respond(f"I've missed you{name_greeting}! It's been {days_ago} days since we last talked. Send a new location if you're somewhere else and a fresh picture of the sky.")


@app.route("/")
def mapview():
	ref = db.reference('/')
	entries = ref.get()

	collection = []		# list to store geojson featurecollection

	for sender in entries:
		entry = entries[sender]

#		if 'photo_url' in entry:
#			url_entry_pic = entry['photo_url']
#		else:
#			url_entry_pic = 'https://s3-external-1.amazonaws.com/media.twiliocdn.com/ACa2dea70cb125daf20c4ac433be77eda4/d7a07ccac2cf9321e82559c82beff7ed'       # random filler pic

		url_entry_pic = entry.get('photo_url', 'https://s3-external-1.amazonaws.com/media.twiliocdn.com/ACa2dea70cb125daf20c4ac433be77eda4/d7a07ccac2cf9321e82559c82beff7ed')

		# construct the geojson feature for this entry
		img_tag = f'<img src=\"{url_entry_pic}\"">'
		description_tag = f'<h3>{entry.get("name", "")}</h3>'

		props = {
			'description': description_tag,
			'photo': img_tag
		}

		cur_feature = Feature(geometry=Point((entry['longitude'], entry['latitude'])), properties=props) # LongLat
		collection.append(cur_feature)

	feature_collection = FeatureCollection(collection)
	# geojson dumps to convert FeatureCollection object into string
	mapdata = dumps(feature_collection, sort_keys=True, indent=4)

	return render_template('index.html', mapdata=mapdata)
