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
channel_id = 0
join_message = ""
get_userlist = ""
leave_message = ""
comment_pattern = re.compile("^#.*")
shut_pattern = re.compile(username + u",\s*уйди.*|" + username + u",\s*вернись.*")


def date_print(message):
    print "[%s] %s" % (str(datetime.now().strftime("%Y-%m-%d %H:%M:%S")), message)
    sys.stdout.flush()


def debug_print(message):
    if crabot_debug == 1:
        try:
            toprint = json.dumps(json.loads(message), indent = 4)
        except:
            toprint = message
        print toprint


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
            cradict[key]["pattern"] = address + cradict[key]["pattern"]
            
        else:
            # handle "list of strings" patterns - this is important for cases when there is multiple patterns for for addressed "reaction"
            patterns_len = cradict[key]["pattern"].__len__()
            for pat in range(0, patterns_len):
                cradict[key]["pattern"][pat] = address + cradict[key]["pattern"][pat]
            cradict[key]["pattern"] = "|".join(cradict[key]["pattern"])
        cradict_patterns[key] = re.compile(cradict[key]["pattern"])
        debug_print(cradict[key]["pattern"])
    date_print("Dictinonary loaded")


class GgClient(WebSocketClient):
    pings_to_greet_users = pings_to_greet_users_default
    silent = 0
    authorized = 0
    cookies = {}
    request_session = requests.Session()
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
            self.init_user(user, 1)
    def greet_users(self, recv_json):
        if self.authorized == 0:
            return
        user_stat = self.user_stat
        timenow = int(time())
        userlist = recv_json["data"]["users"]
        people_to_greet = []
        greet_message = ""
        do_greet = 0
        # Collect list of users to greet, init "lastseen" for those who does not have it
        for user_entry in userlist:
            user = user_entry["name"]
            rights = user_entry["rights"]
            if user == channel_name or user == username:
                continue
            if not user_stat.has_key(user):
                self.init_user(user, 0)
            if not user_stat[user].has_key("lastseen"):
                user_stat[user]["lastseen"] = 0
            if timenow - user_stat[user]["lastseen"] > greet_threshold:
                people_to_greet.append(user)
                do_greet = 1
            user_stat[user]["lastseen"] = timenow
            user_stat[user]["rights"] = rights
        if do_greet == 0:
            return
        # Generate greet message
        for user in people_to_greet:
            greet_message += ", %s" % user
        greet_message = greet_message_template + greet_message 
        r = self.request_session.post("http://goodgame.ru/ajax/dialogs/send", data={'nickname':channel_name, 'text':greet_message}, cookies=self.cookies)
        if r.status_code != 200:
            print "Failed to send greet message %s, code %d" % (greet_message,r.status_code)
    def process_donation(self, recv_json):
        user_stat = self.user_stat
        user = recv_json["data"]["userName"]
        money = float(recv_json["data"]["amount"])
        response = user + ", " + donation_thanks_template
        donation_thanks = json.dumps({"type" : "send_message", "data" : {"channel_id" : channel_id, "text" : response, "hideIcon" : False, "mobile" : False}})
        self.send(donation_thanks)
        self.edit_money(user, int(money/donation_cashback_percent))
    def process_message(self, recv_json):
        global cradict
        if not recv_json["data"].has_key("user_name"):
            date_print ("ERROR! Could not handle previous json, no \"user_name\" field in it... :(")
            print json.dumps(recv_json["data"])
            return
        sender = recv_json["data"]["user_name"]
        user_stat = self.user_stat
        timenow = int(time())
        # ignore bot's messages, or we could get in a loop
        if sender == username:
            return
        # disable bot
        if user_stat[sender].has_key("rights") and user_stat[sender]["rights"] >= 10:
            if shut_pattern.match(recv_json["data"]["parsed"].lower()):
                self.silent = 1 - self.silent
                response = sender + u", как прикажете :cool:"
                enable_message = json.dumps({"type" : "send_message", "data" : {"channel_id" : channel_id, "text" : response, "hideIcon" : False, "mobile" : False}})
                self.send(enable_message)
                return                
        for key in cradict:
            if cradict_patterns[key].match(recv_json["data"]["parsed"].lower()):
                # Check if message should be deleted. Check this before invoking throttling
                if cradict[key]["dodelete"] == 1:
                    del_message = json.dumps({"type" : "remove_message", "data" : {"channel_id" : channel_id, "message_id" : recv_json["data"]["message_id"]}})
                    self.send(del_message)
                # Check if silent mode is enabled
                if self.silent == 1:
                    return
                # Check throttling
                throttling = cradict[key]["throttling"]
                if throttling == 0:
                    throttling = throttling_default
                if throttling > 0:
                    if timenow < cradict[key]["lastused"] + throttling:
                        return
                cradict[key]["lastused"] = timenow
                # Form reply
                if cradict[key]["doreply"] != 0:
                    if cradict[key]["doreply"] == 1:
                        response = sender + ", " + cradict[key]["response"]
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
            r = self.request_session.post("https://goodgame.ru/ajax/chatlogin", data={'login' : username, 'password' : password})
            jresponse = json.loads(r.text)
            self.cookies = r.headers
        r = self.request_session.get("http://api2.goodgame.ru/v2/streams/%s" % channel_name)
        if not r.ok:
            date_print("Critical error, cannot get channel id")
            sys.exit(-1)
        chan_id_response = json.loads(r.text)
        global channel_id
        global join_message
        global get_userlist
        global leave_message
        channel_id = chan_id_response["id"]
        join_message = json.dumps({"type" : "join", "data" : {"channel_id" : channel_id, "hidden" : True}})
        get_userlist = json.dumps({"type" : "get_users_list2", "data" : {"channel_id" : channel_id}})
        leave_message = json.dumps({"type" : "unjoin", "data" : {"channel_id" : channel_id}})
        if username and password and jresponse["result"]:
            self.authorized = 1
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
            debug_print(recv_json["data"])
            date_print("Connecting to channel %d..." % channel_id)
            self.send(join_message)
            return
        if recv_json["type"] == "message":
            # account the message
            debug_print(recv_json["data"])            
            user = recv_json["data"]["user_name"]
            self.count_message(user)
            self.process_message(recv_json)
            return
        if recv_json["type"] == "success_join":
            # successfully joined the channel
            debug_print(recv_json["data"])
            date_print("Joined %s channel!" % recv_json["data"]["channel_streamer"]["name"])
            return
        if recv_json["type"] == "welcome":
            # successfully connected to GG server
            debug_print(recv_json["data"])
            date_print("Established connection to GoodGame server.")
            return
        if recv_json["type"] == "payment":
            # received donation
            debug_print(recv_json["data"])
            self.process_donation(recv_json)
            return
        if recv_json["type"] == "channel_counters":
            debug_print(recv_json["data"])
            self.pings_to_greet_users -= 1
            if self.pings_to_greet_users == 0:
                self.pings_to_greet_users = pings_to_greet_users_default
                self.send(get_userlist)
            return        
        if recv_json["type"] == "users_list":
            debug_print(recv_json["data"])
            self.greet_users(recv_json)
            return
        if recv_json["type"] == "accepted" or recv_json["type"] == "success_unjoin":
            debug_print(recv_json["data"])
            return
        date_print(json.dumps(recv_json))

# Main body

load_cradict()

try:
    ws = GgClient('ws://chat.goodgame.ru:8081/chat/websocket', protocols = ['http-only', 'chat'])
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
