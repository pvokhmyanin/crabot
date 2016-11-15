#!/usr/bin/python
from ws4py.client.threadedclient import WebSocketClient
import json
import requests
from config_crabot import *

class DummyClient(WebSocketClient):
    def opened(self):
        self.send(json.dumps({"type":"auth", "data":{"user_id":"0"}}))
    def closed(self, code, reason=None):
        print "Closed down", code, reason
    def received_message(self, m):
        print json.dumps(json.loads(m.data.decode("utf-8")), indent=4, sort_keys=True)

r = requests.post("https://goodgame.ru/ajax/chatlogin", data={'login': login, 'password': password})
auth_response = r.text

auth_message = json.dumps({"type":"auth", "data":{"user_id":"0"}})
join_message = json.dumps({"type":"join","data":{"channel_id":44451,"hidden":False}})
get_userlist = json.dumps({"type":"get_users_list","data":{"channel_id":44451}})
leave_message = json.dumps({"type":"unjoin","data":{"channel_id":44451}})

try:
    ws = DummyClient('ws://chat.goodgame.ru:8081/chat/websocket', protocols = ['http-only', 'chat'])
    ws.connect()
    ws.send(join_message)
    ws.send(get_userlist)
    ws.run_forever()
except KeyboardInterrupt:
    ws.close()

