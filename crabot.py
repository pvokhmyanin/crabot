#!/usr/bin/python
# -*- coding: utf-8 -*-
from ws4py.client.threadedclient import WebSocketClient
from time import time
from datetime import datetime
import json
import requests
import ast
import re
import unicodedata
import codecs
import sys

# Do not generate .pyc for config_crabot
sys.dont_write_bytecode = True

# import username, password and channel_id from config_crabot.py
from config_crabot import *

cradict_patterns = {}
cradict = {}
join_message = json.dumps({"type" : "join", "data" : {"channel_id" : channel_id, "hidden" : True}})
get_userlist = json.dumps({"type" : "get_users_list2", "data" : {"channel_id" : channel_id}})
leave_message = json.dumps({"type" : "unjoin", "data" : {"channel_id" : channel_id}})
comment_pattern = re.compile("^#.*")

def date_print(message):
    print "[%s] %s" % (str(datetime.now().strftime("%Y-%m-%d %H:%M:%S")), message)

def load_cradict():
    global cradict
    global cradict_patterns
    i = 1
    date_print("Loading dictionary...")
    with codecs.open(cradict_path, "r", encoding='UTF-8') as cradict_file:
        for line in cradict_file:
            if not comment_pattern.match(line):
                try:
                    cradict[i] = ast.literal_eval(line)
                except:
                    continue
                i += 1
    for key in cradict:
        # prepare address variable
        if cradict[key]["address"] == 0:
            address = ""
        if cradict[key]["address"] == 1:
            address = "%s,\s*" % channel_name
        if cradict[key]["address"] == 2:
            address = "%s,\s*" % username
        if type(cradict[key]["pattern"]) is not list:
            # handle simple string patterns
            cradict_patterns[key] = re.compile(address + cradict[key]["pattern"])
        else:
            # handle "list of strings" patterns - this is important for cases when there is multiple patterns for for addressed "reaction"
            patterns_len = cradict[key]["pattern"].__len__()
            for pat in range(0, patterns_len):
                cradict[key]["pattern"][pat] = address + cradict[key]["pattern"][pat]
            pattern_joined = "|".join(cradict[key]["pattern"])
            cradict_patterns[key] = re.compile(pattern_joined)
    date_print("Dictinonary loaded")

class ggClient(WebSocketClient):
    pings_to_greet_users = pings_to_greet_users_default
    us = open(userstat_path, "r")
    try:
        user_stat = ast.literal_eval(us.read())
    finally:
        us.close()
    def init_user(self, user, messages):
        user_stat = self.user_stat
        user_stat[user] = {}
        user_stat[user]["messages"] = messages
        user_stat[user]["money"] = starting_money
        user_stat[user]["lastseen"] = 0
    def edit_money(self, user, money):
        user_stat = self.user_stat
        user_stat[user]["money"] += money
    def count_message(self, user):
        user_stat = self.user_stat
        if user_stat.has_key(user):
            user_stat[user]["messages"] += 1
            if user_stat[user]["messages"] % messages_for_money == 0:
                self.edit_money(user, 1)
        else:
            init_user(user, 1)
    def greet_users(self, recv_json):
        user_stat = self.user_stat
        timenow = int(time())
        userlist = recv_json["data"]["users"]
        people_to_greet = []
        greet_message = ""
        do_greet = 0
        # Collect list of users to greet, init "lastseen" for those who does not have it
        for user_entry in userlist:
            user = user_entry["name"]
            if user == channel_name or user == username:
                continue
            if not user_stat.has_key(user):
                init_user(user, 0)
            if not user_stat[user].has_key("lastseen"):
                user_stat[user]["lastseen"] = 0
            if timenow - user_stat[user]["lastseen"] > greet_threshold:
                people_to_greet.append(user)
                do_greet = 1
            user_stat[user]["lastseen"] = timenow
        if do_greet == 0:
            return
        # Generate greet message
        for user in people_to_greet:
            greet_message += "%s, " % user
        greet_message = greet_message + greet_message_template
        greet_json = json.dumps({"type" : "send_message", "data" : {"channel_id" : channel_id, "text" : greet_message, "hideIcon" : False, "mobile" : False}})
        self.send(greet_json)
    def process_donation(self, recv_json):
        user_stat = self.user_stat
        user = recv_json["data"]["userName"]
        money = float(recv_json["data"]["amount"])
        response = user + donation_thanks_template
        donation_thanks = json.dumps({"type" : "send_message", "data" : {"channel_id" : channel_id, "text" : response, "hideIcon" : False, "mobile" : False}})
        self.send(donation_thanks)
        self.edit_money(user, int(money/donation_cashback_percent))
    def process_message(self, recv_json):
        global cradict
        # ignore bot's messages, or we could get in a loop
        if recv_json["data"]["user_name"] == username:
            return
        for key in cradict:
            if cradict_patterns[key].match(recv_json["data"]["parsed"].lower()):
                # Check if message should be deleted. Check this before invoking throttling
                if cradict[key]["dodelete"] == 1:
                    del_message = json.dumps({"type" : "remove_message", "data" : {"channel_id" : channel_id, "message_id" : recv_json["data"]["message_id"]}})
                    self.send(del_message)
                # Check throttling
                throttling = cradict[key]["throttling"]
                if throttling == 0:
                    throttling = throttling_default
                if throttling > 0:
                    timenow = int(time())
                    if timenow < cradict[key]["lastused"] + throttling:
                        return
                cradict[key]["lastused"] = timenow
                # Form reply
                if cradict[key]["doreply"] != 0:
                    if cradict[key]["doreply"] == 1:
                        response = recv_json["data"]["user_name"] + ", " + cradict[key]["response"]
                    if cradict[key]["doreply"] == 2:
                        response = channel_name + ", " + cradict[key]["response"]
                else:
                    response = cradict[key]["response"]
                # Send reply
                response_json = json.dumps({"type" : "send_message", "data" : {"channel_id" : channel_id, "text" : response, "hideIcon" : False, "mobile" : False}})
                self.send(response_json)
                return
    def opened(self):
        date_print("Obtaining authentication token...")
        if username and password:
            r = requests.post("https://goodgame.ru/ajax/chatlogin", data={'login' : username, 'password' : password})
            jresponse = json.loads(r.text)
        if username and password and jresponse["result"]:
            date_print("Authentication Success")
            date_print("Welcome back, captain %s!" % username)
            user_id = jresponse["user_id"]
            token = jresponse["token"]
            auth_message = json.dumps({"type" : "auth", "data" : {"user_id" : user_id, "token" : token }})
        else:
            date_print("Authentication Failed: %s" % json)
            date_print("Will use guest user...")
            auth_message = json.dumps({"type" : "auth", "data" : {"user_id" : "0"}})
        self.send(auth_message)
    def closed(self, code, reason=None):
        date_print("Connection closed! Reason %s" % reason)
        us = open(userstat_path, "w")
        try:
            us.write(str(self.user_stat))
        finally:
            us.close()        
    def received_message(self, m):
        user_stat = self.user_stat
        recv_json = json.loads(m.data.decode("utf-8"))
        if recv_json["type"] == "success_auth":
            date_print("Connecting to channel %d..." % channel_id)
            self.send(join_message)
            return
        if recv_json["type"] == "message":
            # account the message
            user = recv_json["data"]["user_name"]
            self.count_message(user)
            self.process_message(recv_json)
            return
        if recv_json["type"] == "success_join":
            # successfully joined the channel
            date_print("Joined %s channel!" % recv_json["data"]["channel_streamer"]["name"])
            return
        if recv_json["type"] == "welcome":
            # successfully connected to GG server
            date_print("Established connection to GoodGame server.")
            return
        if recv_json["type"] == "payment":
            # received donation
            self.process_donation(recv_json)
            return
        if recv_json["type"] == "channel_counters":
            self.pings_to_greet_users -= 1
            if self.pings_to_greet_users == 0:
                self.pings_to_greet_users = pings_to_greet_users_default
                self.send(get_userlist)
            return        
        if recv_json["type"] == "users_list":
            self.greet_users(recv_json)
            return
        if recv_json["type"] == "accepted" or recv_json["type"] == "success_unjoin":
            return
        date_print(json.dumps(recv_json))

# Main body

load_cradict()

try:
    ws = ggClient('ws://chat.goodgame.ru:8081/chat/websocket', protocols = ['http-only', 'chat'])
    ws.connect()
    ws.run_forever()
except KeyboardInterrupt:
    ws.send(leave_message)
    ws.close()
    us = open(userstat_path, "w")
    try:
        us.write(str(ws.user_stat))
    finally:
        us.close()
