import socket
from datetime import datetime
from threading import Thread, Lock
import re
from re import Match
import json

client_sockets = {}
client_lock = Lock()

# 用户表，对应用户名和密码
user_list = {
    "user":"xxx" # 键值对为账号密码
}

# 用户的好友信息，key可以是任意的，val为对应的好友
user_data = {
    "user1":{
        "friend1": "user2",
        "friend2": "于梓垚giegie"
    },
    "user2":{
        "friend1": "user1",
        "friend2": "于梓垚giegie"
    },
    "于梓垚giegie":{
        "friend1": "user1",
        "friend2": "user2"
    }
}

def client_handler(c: socket.socket, addr):
    print(f"{now_time()} new connection: {addr}, now start thread.")
    while True:
        try:
            rcv = c.recv(1024).decode().strip()
            if rcv.startswith("ariyflow/HNU-ICU@"):
                rcv = rcv[17:]
                if rcv.startswith("quit"): # 退出指令
                    print(f"{now_time()} quit the connection: {addr}")
                    json_data = re.compile(r"quit:#(?P<json_data>.*?)#").search(rcv).group("json_data") # type: ignore
                    json_data = json.loads(json_data)
                    del client_sockets[json_data["user"]] # type: ignore
                    print(f"{json_data['user']} socket already delete.")
                    break
                try:
                    print(f"{now_time()} receive data: \"{rcv}\"")
                    
                    if rcv == "test":
                        c.send("ariyflow/HNU-ICU@test".encode())
                    elif rcv.startswith("login"): # 登录命令
                        obj = re.compile(r"login:username=(?P<username>.*?)&password=(?P<password>.*)", re.S)
                        data: Match = obj.search(rcv) # type: ignore
                        username = data.group("username")
                        password = data.group("password")
                        if user_list.get(username) is not None: # 用户列表中存在用户名
                            if user_list[username] == password: # 密码匹配，进入用户加载逻辑
                                c.send(f"ariyflow/HNU-ICU@data:[user_friends]#{json.dumps(user_data[username])}#".encode())
                                
                                c.send("ariyflow/HNU-ICU@login:success".encode())
                                with client_lock:
                                    client_sockets[username] = c
                            else: # 密码不匹配，返回
                                c.send("ariyflow/HNU-ICU@login:password-error".encode())
                        else: # 不存在，直接返回
                            c.send("ariyflow/HNU-ICU@login:username-error".encode())
                    elif rcv.startswith("send"):
                        parser = re.compile(r"send:\[(?P<send_type>.*?)\]#(?P<json_data>.*?)#",re.S)
                        data = parser.search(rcv) # type: ignore
                        send_type = data.group("send_type")
                        msg = data.group("json_data")
                        msg = json.loads(msg)
                        
                        if send_type == "chat_message": # 发送来的数据为聊天记录
                            """此时需要更新聊天记录"""
                            from_socket = client_sockets.get(msg["from"])
                            to_socket = client_sockets.get(msg["to"])
                            
                            if from_socket:
                                from_socket.send(f"ariyflow/HNU-ICU@data:[chat_content]#{json.dumps(msg)}#".encode())
                            if to_socket:
                                to_socket.send(f"ariyflow/HNU-ICU@data:[chat_content]#{json.dumps(msg)}#".encode())
                        elif send_type == "chat_room_command": # 聊天室指令
                            json_data = json.dumps({
                                "user": msg["user"],
                                "type": "enter_msg" if msg["command"] == "enter" else "quit_msg",
                                "msg": "" # 命令的返回不需要信息                                
                                })

                            # 向所有建立连接的socket广播该信息
                            print(f"send data to all client - data:[chat_room_content]#{json_data}#")
                            for client_socket in client_sockets.values():
                                client_socket.send(f"ariyflow/HNU-ICU@data:[chat_room_content]#{json_data}#".encode())
                                
                        elif send_type == "chat_room_message": # 聊天室消息
                            json_data = json.dumps({
                                "user": msg["user"],
                                "type": "msg",
                                "msg": msg["msg"]
                            })
                            print(f"send data to all client - data:[chat_room_content]#{json_data}#")
                            for client_socket in client_sockets.values():
                                client_socket.send(f"ariyflow/HNU-ICU@data:[chat_room_content]#{json_data}#".encode())
                    # if rcv == "于梓垚":
                    #     c.send("于梓垚哥哥么么么".encode())
                    # else:
                    #     c.send(rcv.upper().encode())
                except Exception as e:
                    print(f"{now_time()} receive invalid data.({addr})")
                    print(e)
        except:
            print("run time error. may be data encode is not correct.")
            print(e)
    
    c.close()


def now_time():
    date = datetime.now()
    return f"[{date.year}-{date.month}-{date.day} {date.hour}:{date.minute}:{date.second}]"


if __name__ == "__main__":
    s = socket.socket()
    host = "0.0.0.0"
    port = 12345
    print(host)
    s.bind((host, port))

    s.listen(5)

    while True:
        try:
            c, addr = s.accept()
            
            client_thread = Thread(target=client_handler, args=(c, addr), daemon=True)
            client_thread.start()
        except:
            pass