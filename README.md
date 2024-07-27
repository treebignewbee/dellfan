# dellfan
戴尔服务器R730/R730xd风扇调速静音

用于捡垃圾的戴尔服务器在自己家中使用时，调节风扇转速，从而达到静音的效果，避免原地起飞。

截图:
![image](https://github.com/user-attachments/assets/f2c7999e-f348-4fbe-a78b-a7ef591eaf15)

用法：
1.打开程序目录，在DellFanController.ini中配置戴尔IdRAC配置信息，包括IP，用户名，密码
2.点击“dellfan.exe”启动，等待读取传感器数据，通过“ipmitool.exe”发送命令行读取数据。
3.选择对应的功能，调节风扇转速。


