#!/usr/bin/python
# -*- coding: utf-8 -*-
from ws4py.client.threadedclient import WebSocketClient
import json
import requests
import ast
import pprint
import re

#import username, password and channel_id from config_crabot.py
from config_crabot import *

pp = pprint.PrettyPrinter(indent=4)

class ggClient(WebSocketClient):
    us = open("userstat.txt", "r")
    try:
        user_stat = ast.literal_eval(us.read())
    finally:
        us.close()
    def opened(self):
        print "Connecting to channel %d..." % channel_id

        join_message = json.dumps({"type":"join","data":{"channel_id":channel_id,"hidden":True}})
        get_userlist = json.dumps({"type":"get_users_list2","data":{"channel_id":channel_id}})
        leave_message = json.dumps({"type":"unjoin","data":{"channel_id":channel_id}})

        if username and password:
            r = requests.post("https://goodgame.ru/ajax/chatlogin", data={'login': username, 'password': password})
            jresponse = json.loads(r.text)
        if username and password and jresponse["result"]:
            print "Authentication Success"
            print "Welcome back, captain %s!" % username
            user_id = jresponse["user_id"]
            token = jresponse["token"]
            auth_message = json.dumps({"type":"auth", "data":{"user_id" : user_id, "token" : token }})
        else:
            print "Authentication Failed: %s" % json
            print "Will use guest user..."
            auth_message = json.dumps({"type":"auth", "data":{"user_id":"0"}})
        self.send(auth_message)
        self.send(join_message)
    def closed(self, code, reason=None):
        us = open("userstat.txt", "w")
        try:
            us.write(str(self.user_stat))
        finally:
            us.close()        
    def received_message(self, m):
        user_stat = self.user_stat
        recv_json = json.loads(m.data.decode("utf-8"))
        if recv_json["type"] == "message":
            user = recv_json["data"]["user_name"]
            if user_stat.has_key(user):
                user_stat[user]["messages"] += 1
                if user_stat[user]["messages"] % 10 == 0:
                    user_stat[user]["money"] += 1
            else:
                user_stat[user] = {}
                user_stat[user]["messages"] = 1
                user_stat[user]["money"] = 0
            print "%s[#%d,$%d]: %s" % (user, user_stat[user]["messages"], user_stat[user]["money"], recv_json["data"]["parsed"])
            crab_pattern = re.compile(".*:crab:.*")
            if crab_pattern.match(recv_json["data"]["parsed"]):
                send_text = u"%s, На этом канале крабы - священные животные. Пожалуйста воздержитесь от упоминания их в негативном свете." % user
                crab_warn_message = json.dumps({"type":"send_message","data":{"channel_id":channel_id,"text":send_text,"hideIcon": False,"mobile":False}})
                self.send(crab_warn_message)
                del_message = json.dumps({"type":"remove_message","data":{"channel_id":channel_id,"message_id":recv_json["data"]["message_id"]}})
                self.send(del_message)
        else:
            if recv_json["type"] != "channel_counters":
                print json.dumps(recv_json)
try:
    ws = ggClient('ws://chat.goodgame.ru:8081/chat/websocket', protocols = ['http-only', 'chat'])
    ws.connect()
    ws.run_forever()
except KeyboardInterrupt:
    ws.close()
    us = open("userstat.txt", "w")
    try:
        us.write(str(ws.user_stat))
    finally:
        us.close()
    print ""
    pp.pprint(ws.user_stat)

'''

>>> {"type":"users_list","data":{"channel_id":44451,"clients_in_channel":"4","users_in_channel":2,"users":[{"id":"457651","name":"NafanyaShow","rights":20,"premium":false,"premiums":[],"banned":false,"baninfo":false,"payments":"0","hidden":false,"stuff":"0"},{"id":"647206","name":"destroer1990","rights":10,"premium":true,"premiums":[0],"banned":false,"baninfo":false,"payments":"6","hidden":false,"stuff":"0"}]}}

'''
