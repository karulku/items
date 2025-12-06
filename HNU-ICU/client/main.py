from PySide6.QtWidgets import(
    QApplication, QMainWindow, QPushButton, QPlainTextEdit, QLabel,
    QTabWidget, QLineEdit, QListWidget, QMessageBox
)
from PySide6.QtCore import QFile, QThread, Signal, QTimer
from PySide6.QtUiTools import QUiLoader
import sys
import socket
import requests
from datetime import datetime
from receiveThread import receiveThread
import re
from re import Match
import json

"""
通信规则：
向服务器发送数据时，要求开头固定为ariyflow/HNU-ICU
后面可以跟数据
登录请求：
    ariyflow/HNU-ICU@login:username={username}&password={password}
测试连接：
    ariyflow/HNU-ICU@test
    发出该信息后，服务器会原样返回信息
退出连接：
    ariyflow/HNU-ICU@quit:#{"user":"xxx"}#
发送数据：
    ariyflow/HNU-ICU@send:[send_type]#{json_data}#
        send_type: 发送的数据类型
            chat_message - 聊天内容
            chat_room_command - 聊天室指令
            chat_room_message - 聊天室内容发送
        json_data: 发送的数据
            chat_message - 如果send_type为chat_message则包含三条信息，from, to, message，分别表示发送方，接收方，数据
            chat_room_command - {"user":"username", "command":"issue"} 发送的数据为用户名，接入即可，command为命令：
                enter - 进入聊天室
                quit - 退出聊天室 #注意这部分内容在服务器端限制了，只能有这两条指令，如果需要添加指令需要到服务器端修改逻辑#
            chat_room_message - {"user":"username", "msg":"message"} 发送的用户名，以及要发送的数据
            

接收信息：
    ariyflow/HNU-ICU@login:{status_code}
        status_code:
            success 登陆成功； password-error 密码错误；username-error 用户不存在
    ariyflow/HNU-ICU@data:[data_type]#{json_data}#
        data_type: 数据的类型
            user_friends - 好友列表；
            chat_content - 聊天记录；服务器收到一条聊天记录信息后，向发送方和接收方同步更新信息
            chat_room_content - 聊天室内容
        json_data：
            json格式传送的数据
            chat_room_content - {"user":"username","type":"xxx","msg":"message"} type类型：
                enter_msg - 有人进入聊天室的消息
                quit_msg - 有人离开聊天室的消息
                msg - 有人发送了消息
"""

ADDR = "8.140.232.178"
PORT = 12345

def now_time():
    date = datetime.now()
    return f"[{date.year}-{date.month}-{date.day} {date.hour}:{date.minute}:{date.second}]"

def get_external_ip(timeout=5):
    """获取本机外网IP（通过第三方API）"""
    # 常用公网IP查询API（可替换为其他可靠API）
    api_list = [
        "https://icanhazip.com",    # 简洁（仅返回IP）
    ]
    
    for api in api_list:
        try:
            response = requests.get(api, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'})
            if response.status_code == 200:
                external_ip = response.text.strip()  # 去除换行符
                return external_ip
        except requests.exceptions.RequestException:
            continue  # 某个API失败，尝试下一个
    
    return "获取外网IP失败（网络异常或API不可用）"

class HNUICU(QMainWindow):
    def __init__(self, par: QApplication):
        super().__init__()
        self.par = par
        
        self.win = QUiLoader().load(QFile("test.ui"))
        self.setCentralWidget(self.win)
        self.setWindowTitle("HNU-ICU聊天app")
        self.setGeometry(400,300,720,540)
        
        self.soc = socket.socket() # 与服务器通信的socket
        self.soc.connect((ADDR, PORT))
        
        self.soc.send(f"[{now_time()}] ip \"{get_external_ip()}\" try to build connection.".encode("utf-8")) # 开始后发送连接的信号
        
        self.rcvThread = receiveThread(self, self.soc) # 控制接收信息的线程
        self.rcvThread.rcv_data.connect(self.rcv_data_parser)
        self.rcvThread.start()
        
        self.chat_update_timer = QTimer() # 每100ms执行一次update，更新chat窗口的定时器
        self.chat_update_timer.timeout.connect(self.chat_update_handler)
        self.chat_update_timer.start(1000)
        
        self.now_user = "" # 当前的用户
        self.chat_text_list = [] # 聊天记录
        self.currentIndex = 0 # 临时保存当前tab的索引
        
        self.load_widgets() # 加载组件
        
        self.par.aboutToQuit.connect(self.quit_handler)
    
    # 组件加载的函数
    def load_widgets(self):
        self.tabWidget: QTabWidget = self.win.findChild(QTabWidget, "tabWidget") # type: ignore
        
        # 登录栏的组件
        self.user_edit: QLineEdit = self.win.findChild(QLineEdit, "user_edit") # type: ignore 用户名
        self.pswd_edit: QLineEdit = self.win.findChild(QLineEdit, "pswd_edit") # type: ignore 密码
        self.login_btn: QPushButton = self.win.findChild(QPushButton, "login_btn") # type: ignore 登录按钮
        
        # 好友栏的组件
        self.friend_list: QListWidget = self.win.findChild(QListWidget, "friend_list") # type: ignore 好友列表
        self.refresh_btn: QPushButton = self.win.findChild(QPushButton, "refresh_btn") # type: ignore 刷新按钮
        
        # 聊天栏的组件
        self.chat_text: QPlainTextEdit = self.win.findChild(QPlainTextEdit, "chat_text") # type: ignore 聊天栏
        self.send_edit: QLineEdit = self.win.findChild(QLineEdit, "send_edit") # type: ignore 发送的输入栏
        self.send_btn: QPushButton = self.win.findChild(QPushButton, "send_btn") # type: ignore 发送按钮
        
        # 聊天室的组件
        self.chat_room_text: QPlainTextEdit = self.win.findChild(QPlainTextEdit, "chat_room_text") # type: ignore
        self.chat_room_edit: QLineEdit = self.win.findChild(QLineEdit, "chat_room_edit") # type: ignore
        self.chat_room_send: QPushButton = self.win.findChild(QPushButton, "chat_room_send") # type: ignore
        
        # 按钮绑定函数
        self.login_btn.clicked.connect(self.login_handler)
        self.refresh_btn.clicked.connect(self.refresh_handler)
        self.send_btn.clicked.connect(self.send_message_handler)
        self.chat_room_send.clicked.connect(self.chat_room_send_handler)
        
        self.tabWidget.currentChanged.connect(self.currentIndexChangedHandler) # tab切换的事件
        self.chat_room_edit.returnPressed.connect(self.chat_room_send_handler) # enter按键的绑定，发送数据按钮的处理一致
        self.send_edit.returnPressed.connect(self.send_message_handler)
        
        self.friend_list.currentItemChanged.connect(self.friend_list_item_changed_handler) # 好友列表切换的事件
        
    # 登录处理的函数
    def login_handler(self):
        username = self.user_edit.text().strip()
        password = self.pswd_edit.text().strip()
        if username and password:
            self.soc.send(f"""
                          ariyflow/HNU-ICU@login:username={username}&password={password}
                          """.encode())
            
        else:
            QMessageBox.about(None, "提示", "请输入完整的用户名和密码！")
        # self.soc_deliver("login handler.")
    
    def refresh_handler(self):
        pass
    
    def quit_handler(self): # 退出逻辑
        
        self.save_chat_data(self.friend_list.currentItem().text())
        
        if self.rcvThread and self.rcvThread.is_running.is_set():
            self.rcvThread.is_running.clear()
            self.soc.send("ariyflow/HNU-ICU@test".encode())
            self.rcvThread.quit()
            self.rcvThread.wait()
            
        if self.soc:
            json_data = json.dumps({
                "user":self.now_user
            })
            self.soc.send(f"ariyflow/HNU-ICU@quit:#{json_data}#".encode())
            self.soc.close()
    
    def send_message_handler(self): # 发送数据
        msg = self.send_edit.text()
        if not msg:
            return
        dat = {
            "from": self.now_user,
            "to": self.friend_list.currentItem().text(),
            "message": msg
        }
        dat = json.dumps(dat)
        self.soc.send(f"ariyflow/HNU-ICU@send:[chat_message]#{dat}#".encode())
        print(f"send data: send:[chat_message]#{dat}#")
        self.send_edit.clear()
    
    def rcv_data_parser(self, rcv: str): # 处理服务器传来的数据
            if rcv.startswith("login"): # 登录逻辑
                if rcv.endswith("password-error"):
                    QMessageBox.about(None, "提示", "密码错误！")
                elif rcv.endswith("username-error"):
                    QMessageBox.about(None, "提示", "未找到用户！")
                elif(rcv.endswith("success")):
                    self.now_user = self.user_edit.text().strip()
                    self.friend_list.setCurrentRow(0)
                    if self.friend_list.currentItem() is not None:
                        self.load_chat_data(self.friend_list.currentItem().text())
                    QMessageBox.about(None, "提示", "登录成功！")
            elif rcv.startswith("data"): # 传来的是数据
                parser = re.compile(r"data:\[(?P<data_type>.*?)\]#(?P<json_data>.*?)#")
                data: Match = parser.search(rcv) # type: ignore
                data_type = data.group("data_type")
                if data_type == "user_friends": # 传来的数据是好友列表
                    friends_list: dict = json.loads(data.group("json_data")) # 好友列表。只有value有效
                    
                    # print(friends_list) # 这里替换成修改好友列表的处理
                    self.friend_list.clear()
                    
                    # 更新好友列表
                    self.friend_list.addItems(friends_list.values()) # type: ignore
                    self.chat_text_list = []*(len(friends_list)) # 生成每一个好友对应的聊天记录列表
                elif data_type == "chat_content": # 传来的是聊天记录
                    # print("聊天记录") # 此处修改为添加聊天记录的处理
                    # print(data.group("json_data"))
                    msg: dict = json.loads(data.group("json_data")) # from to message
                    
                    self.chat_text.appendPlainText(f"{msg["from"]}: {msg["message"]}")
                    if self.friend_list.currentItem() is not None:
                        self.save_chat_data(self.friend_list.currentItem().text())
                    
                elif data_type == "chat_room_content":
                    if not self.now_user:
                        return
                    
                    json_data = json.loads(data.group("json_data")) # user, type, msg
                    # print(json_data)
                    if json_data["type"] == "enter_msg":
                        html = f"""
                            <span style='color: blue;'>"{json_data["user"]}进入聊天室"</span>
                        """
                        self.chat_room_text.appendHtml(html)
                    elif json_data["type"] == "quit_msg":
                        html = f"""
                            <span style='color: red;'>"{json_data["user"]}退出聊天室"</span>
                        """
                        self.chat_room_text.appendHtml(html)
                    elif json_data["type"] == "msg":
                        html = f"""
                            <span style='color: black;'>{json_data["user"]}:{json_data["msg"]}</span>
                        """
                        self.chat_room_text.appendHtml(html)
                
    
    # 保存聊天记录的函数
    def chat_update_handler(self):
        pass
        # idx = self.friend_list.currentIndex()
        # if self.friend_list.currentItem() is not None:
        #     self.save_chat_data(self.friend_list.currentItem().text())
    
    # 聊天室发送处理
    def chat_room_send_handler(self):
        if self.now_user:
            text = self.chat_room_edit.text()
            if text:
                data = json.dumps({
                    "user":self.now_user,
                    "msg":text
                })
                self.soc.send(f"ariyflow/HNU-ICU@send:[chat_room_message]#{data}#".encode())
                self.chat_room_edit.clear()
    
    # 当前标签改变的处理
    def currentIndexChangedHandler(self):
        # 切换前的tab处理例程
        if self.currentIndex == 1:
            if self.now_user:
                json_data = json.dumps({
                    "user": self.now_user,
                    "command": "quit"
                })
                print(f"send data: send:[chat_room_command]#{json_data}#")
                self.soc.send(f"ariyflow/HNU-ICU@send:[chat_room_command]#{json_data}#".encode())
        
        self.currentIndex = self.tabWidget.currentIndex()
        
        # 切换后的tab处理例程
        if self.currentIndex == 1: # 切换后进入聊天室
            if self.now_user: # 如果当前已经登录，发送进入的消息
                json_data = json.dumps({
                    "user": self.now_user,
                    "command": "enter"
                })
                print(f"send_data: send:[chat_room_command]#{json_data}#")
                self.soc.send(f"ariyflow/HNU-ICU@send:[chat_room_command]#{json_data}#".encode())
    
    # 好友列表切换处理
    def friend_list_item_changed_handler(self, now_item, old_item):
        if old_item and now_item:
            self.save_chat_data(old_item.text())
            self.chat_text.clear()
            self.chat_room_text.clear()
            self.load_chat_data(now_item.text())
    
    # 保存聊天记录
    def save_chat_data(self, save_friend: str):
        if self.now_user: # 如果登录，保存信息
            
            last_data: dict = {} # 原来保存的内容
            with open("chat_data.json", mode = "r", encoding = "utf-8") as file:
                last_data = json.loads(file.read())
                
            json_data = {
                "chat_room": self.chat_room_text.toPlainText(),
                save_friend: self.chat_text.toPlainText()
            }
            
            if self.now_user not in last_data:
                last_data[self.now_user] = {}
            last_data[self.now_user]["chat_room"] = json_data["chat_room"]
            last_data[self.now_user][save_friend] = json_data[save_friend]
            # if self.now_user in last_data:
            #     last_data[self.now_user].update(json_data)
            # else:
            #     last_data[self.now_user] = json_data

                
            with open("chat_data.json", mode = "w",encoding = "utf-8") as file:
                file.write(json.dumps(last_data))
                print("data save sucess.")
                print(last_data)
    
    # 加载聊天记录
    
    def load_chat_data(self, target_friend: str):
        if self.now_user:
            last_data: dict = {}
            with open("chat_data.json", mode="r", encoding = "utf-8") as file:
                last_data = json.loads(file.read())
                
            if self.now_user in last_data and target_friend in last_data[self.now_user]:
                self.chat_text.appendPlainText(last_data[self.now_user].get(target_friend)) # type: ignore
                self.chat_room_text.appendPlainText(last_data[self.now_user].get("chat_room"))
                print("chat data import sucess.")
                print(last_data[self.now_user].get(target_friend))
            
            
        
    
if __name__ == "__main__":
    app = QApplication()
    win = HNUICU(app)
    win.show()
    sys.exit(app.exec())