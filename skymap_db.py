#!/usr/bin/env python3
#
# skymap_db - customized library for sqlite 3
# by Nathalie Collins <nathalie@ideo.org>
# let's call this version 0.0.1 - confidence?
#
import sqlite3

__version__ = '0.0.1'

class SkyMapDB:
	# class attributes
	dbname = ""
	tablename = "entries"

	# initialize a SkyMapDB object using the given sql database file
	def __init__(self, filename):
		self.dbname = filename

	# connect to the database
	def connect(self):
		print("Trying to connect...", end =" ")
		
		# connect to the database + save handle to global
		try:
			self.db = sqlite3.connect(self.dbname)
			self.cur = self.db.cursor() # get cursor
			self.cur.execute("CREATE TABLE IF NOT EXISTS entries (id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT, latitude REAL, longitude REAL, region TEXT, country TEXT, photo_url TEXT)")
			self.db.commit()
			print("success")

		except Error as e:
			print("error!")
			print(e)

	# check whether the sender currently exists in the database
	def sender_exists(self, sender):
		query = "SELECT COUNT(*) FROM entries WHERE sender = ?"
		self.cur.execute(query, (sender,))
		#self.cur.execute("SELECT COUNT(*) FROM entries WHERE sender = ?", (sender,))
		count = self.cur.fetchone()[0]
		if count > 0:
			return True
		else:
			return False

	# check whether this sender already has a photo in the database
	def photo_exists(self, sender):
		query = "SELECT photo_url FROM entries WHERE sender = ?"
		self.cur.execute(query, (sender,))
		db_photo_url = self.cur.fetchone()[0]
		if db_photo_url == "":
			return False
		else:
			return True

	# update the photo for sender -- needs error-handling
	def update_photo(self, sender, photo_url):
		query = "UPDATE entries SET photo_url = ? WHERE sender = ?"
		self.cur.execute(query, (photo_url, sender))
		self.db.commit()
		self.update_timestamp(sender)

	# add an entry with the sender's phone number and location
	def add_entry(self, sender, latitude, longitude, region, country):
		print(f'check whether {sender} exists in the database')
		if self.sender_exists(sender) is False:
			print(f'insert row for {sender}')
			query = "INSERT INTO entries (sender, latitude, longitude, region, country) VALUES (?, ?, ?, ?, ?)"
			self.cur.execute(query, (sender, latitude, longitude, region, country))
		else:
			print(f'updating current row for {sender}')
			query = "UPDATE entries SET latitude = ?, longitude = ?, region = ?, country = ? WHERE sender = ?"
			self.cur.execute(query, (latitude, longitude, region, country, sender))
		self.db.commit()
		self.update_timestamp(sender)

	# remove all rows with sender's phone number
	def remove_entry(self, sender):		
		print(f'Removing all rows related to {sender}')
		query = "DELETE from entries WHERE sender = ?"
		self.cur.execute(query, (sender,))
		self.db.commit()

	# how long ago did we talk in days?
	def last_interaction(self, sender):
		query = "SELECT CAST(JulianDay('now') - JulianDay(timestamp) AS integer) FROM entries WHERE sender = ?"
		self.cur.execute(query, (sender,))
		days = self.cur.fetchone()
		print(type(days[0]))
		return days[0]

	# set that timestamp to now
	def update_timestamp(self, sender):
		query = "UPDATE entries SET timestamp = datetime('now') WHERE sender = ?"
		self.cur.execute(query, (sender,))
		self.db.commit()

	# return a list of entries to display on the map
	def get_map_entries(self):
		query = "SELECT latitude, longitude, photo_url FROM entries"
		self.cur.execute(query)
		rows = self.cur.fetchall()
		return rows

	def disconnect(self):
		self.db.close()
		print('close')

def main():
	whatsapp_id = "whatsapp:+14085058305"
	db_api = SkyMapDB('data/skymap.db')

	# check whether whatsapp_id exists as a sender in the database
	val = db_api.sender_exists(whatsapp_id)
	print(f"Sender {whatsapp_id} exists in database: {val}")

	db_api.disconnect()

if __name__ == '__main__': main()
