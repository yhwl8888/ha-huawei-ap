# Huawei Access Point — Home Assistant 集成

把华为**商用 AP**（AirEngine / eKit / 企业 FAT AP）接入 Home Assistant，读取设备健康度、终端列表与 AP 拓扑，无需 SNMP、无需云账号。

> 非官方集成，与华为技术有限公司无关联。请自行承担使用风险。

---

## 1. 实测设备

本集成在以下真实设备上完成开发与验证：

| 项目 | 值 |
|---|---|
| 型号 | **Huawei AirEngine5761-11W** |
| 固件 | VRP 5.170（AirEngine 5700 V200R023C00SPC100） |
| 工作模式 | FAT（Leader AP，独立组网） |
| 管理规模 | 3 台 AP（本机 + 2 × AP4050DE-B-S） |
| 终端规模 | 18 个（2.4G 12 / 5G 6） |
| 管理地址 | 192.168.1.50 |

其他 AirEngine / eKit 型号理论上兼容，命令不可用时集成会自动跳过对应实体。

**不适用**：华为家用路由器（HiLink / 智慧生活生态）、被 AC 云管理的 FIT AP、华为 ONT 光猫。

---

## 2. 为什么走 SSH 而不是 Web 接口

最初的方案是复用设备自带的 Web 网管（`/login.cgi` + `/config.cgi` NETCONF 通道）。协议已完整逆向出来，但实测撞上两个死结：

| 问题 | 现象 |
|---|---|
| **Web 会话只允许 1 个** | 第二次登录立刻返回 `ErrorMsg=1012`（可登录用户数已满）。对一个常驻轮询的集成来说，这意味着只要有人在浏览器里打开管理页，集成就会掉线 |
| **会话 Cookie 不被接受** | `/login.cgi` 成功并下发 `SessionID`，但带着它访问 `/config.cgi` 一律返回 **HTTP 450 `Return Login Page`** |

改用 SSH（22 端口，banner `SSH-2.0-HUAWEI-1.5`）后两个问题都消失，且 CLI 输出比 NETCONF 通道干净得多。Web 协议逆向结论保留在[附录](#附录web-协议逆向记录)中备查。

---

## 3. 工作原理

### 3.1 传输

一条 SSH 连接、一个 `vt100` PTY 会话，批量执行多条 `display` 命令，按提示符切分结果，然后关闭连接。

**设备要求 PTY**：裸 SSH exec 通道（不带 `-tt`）返回空 body，这是接入时最容易踩的坑。

### 3.2 两个必须处理的设备怪癖

都在 `ssh_client.py` 里做了处理：

| 怪癖 | 处理方式 |
|---|---|
| **新 PTY 的第一条命令被吞掉** | 先发一条空行充当牺牲品，再发真实命令 |
| **长输出分页** | 会话开始先执行 `screen-length 0 temporary`，并给足生效时间 |

写入节奏也要控制——VRP 的 stdin 有缓冲，写太快会丢行，因此每条命令之间留 350ms。

### 3.3 数据来源

| 数据 | 命令 |
|---|---|
| 型号 / 固件 / 运行时长 / 工作模式 | `display version` |
| CPU | `display cpu-usage` |
| 内存 | `display memory-usage` |
| 温度（10 个传感器） | `display temperature all` |
| 终端列表 | `display station all` |
| AP 拓扑 / 供电状态 | `display ap all` |
| 射频 / 信道 | `display radio all` |
| 接口 | `display interface brief` |

`display station assoc-info`、`display device`、`display power` 在该固件上**不存在**，不要用。

### 3.4 解析器

`parser.py` 中每个正则都是对着真实输出写的，并用离线快照验证过 **25/25 字段全部命中**。几个容易踩的点：

- CPU 带小数：`CPU   Usage: 13.2%   Max: 76.9%`
- 温度是表格，取最大值而非最后一个数字
- AP/Uptime 是 VRP 紧凑格式：`103D:7H:26M:48S`
- 供电不足体现在 `display ap all` 的 ExtraInfo 列（`P` 标记）

---

## 4. 安装

### 方式 A：HACS

1. HACS → 右上角菜单 → 自定义存储库
2. 添加本仓库，类别选「集成」
3. 搜索 **Huawei Access Point** 安装并重启

### 方式 B：手动

```bash
cp -r custom_components/huawei_ap /path/to/homeassistant/config/custom_components/
```

重启 Home Assistant。首次启动会自动安装依赖 `asyncssh`。

---

## 5. 配置

**设置 → 设备与服务 → 添加集成 → 搜索「Huawei Access Point」**

| 字段 | 说明 | 建议 |
|---|---|---|
| 主机地址 | AP 的 IP | `192.168.1.50` |
| 用户名 | SSH 管理员账号 | `admin` |
| 密码 | SSH 密码 | — |
| SSH 端口 | 默认 22 | `22` |
| 轮询间隔 | 秒，范围 15–600 | `30` |

配置时会执行一次完整探测：SSH 登录 + `display version`。两项都通过才创建条目。

**前提**：设备必须开启 SSH 服务，且账号具备管理员权限。

```
system-view
stelnet server enable
aaa
 local-user admin service-type ssh terminal
```

---

## 6. 实体

### 传感器

| 实体 | 单位 | 默认启用 | 说明 |
|---|---|---|---|
| `sensor.*_cpu_usage` | % | 是 | CPU 使用率 |
| `sensor.*_cpu_peak` | % | 否 | CPU 历史峰值 |
| `sensor.*_memory_usage` | % | 是 | 内存使用率 |
| `sensor.*_memory_used` | MB | 否 | 已用内存 |
| `sensor.*_temperature` | °C | 是 | 温度（10 传感器均值） |
| `sensor.*_temperature_max` | °C | 否 | 最高传感器温度 |
| `sensor.*_uptime` | s | 是 | 运行时长 |
| `sensor.*_client_count` | — | 是 | 关联终端数，属性含完整终端表 |
| `sensor.*_client_count_24g` | — | 否 | 2.4G 终端数，属性含射频明细 |
| `sensor.*_client_count_5g` | — | 否 | 5G 终端数 |
| `sensor.*_ap_count` | — | 是 | 在线 AP 数，属性含 AP 拓扑 |
| `sensor.*_interfaces_up` | — | 否 | 在线接口数，属性含各接口利用率 |

### 二进制传感器

| 实体 | 设备类 | 说明 |
|---|---|---|
| `binary_sensor.*_reachable` | connectivity | 设备是否可达 |
| `binary_sensor.*_power_insufficient` | problem | **供电不足**（PoE 功率不够，功能受限） |
| `binary_sensor.*_temperature_alarm` | problem | 传感器状态异常 |
| `binary_sensor.*_clients_present` | — | 是否有终端在线 |

### 设备追踪

每个关联终端自动创建一个 `device_tracker`，属性包含 **IP、SSID、所属 AP、频段、协议、RSSI、收发速率、VLAN**。

终端下线后实体转为 `not_home` 而不是消失，历史记录得以保留。

### 按钮

`button.*_restart` — 重启设备。**注意：会让所有接入终端断网 1–2 分钟。**

---

## 7. 诊断脚本

接入 HA 之前，建议先跑一次诊断，确认设备命令集与解析结果。零依赖，只用系统 OpenSSH。

```bash
cd huawei_ap
bash tools/probe_huawei_ap.sh -H 192.168.1.50 -u admin -p '你的密码'

# 只验证登录
bash tools/probe_huawei_ap.sh -H 192.168.1.50 -p '你的密码' --login-only

# 保存原始输出便于排查
bash tools/probe_huawei_ap.sh -H 192.168.1.50 -p '你的密码' --dump raw.txt
```

输出示例：

```
======================================================================
华为 AP 诊断  ->  admin@192.168.1.50:22
======================================================================
[OK  ] SSH 登录成功

设备摘要
  型号      : AirEngine5761-11W
  固件      : 5.170 AirEngine 5700 V200R023C00SPC100
  工作模式  : FAT
  uptime is 14 weeks, 5 days, 7 hours, 35 minutes

----------------------------------------------------------------------
命令可用性
----------------------------------------------------------------------
  [ OK ] display cpu-usage  (4 行)
  [ OK ] display memory-usage  (4 行)
  ...
```

---

## 8. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `无法连接设备` | 地址 / 端口错，或 SSH 未开启 | `ssh admin@<ip>` 手动确认 |
| `用户名或密码错误` | 凭据错 | 手动 SSH 验证 |
| `命令被设备拒绝` | 账号权限不足 | 需要 `service-type ssh terminal` 的管理员账号 |
| 部分实体「未知」 | 该型号无此命令 | 跑诊断脚本，看哪条 MISS |
| 实体全部不可用 | 轮询过快触发限制 | 调大间隔到 60s |
| 连接偶发超时 | VTY 会话数占满 | `display users` 确认没有残留会话 |

### 调试日志

```yaml
logger:
  default: warning
  logs:
    custom_components.huawei_ap: debug
```

---

## 9. 已知限制

- 未实现写入类服务（改 SSID、开关射频、踢终端等），目前只读 + 重启
- 重启按钮未做二次确认，误触会断网
- 终端没有主机名反查，只有 MAC / IP
- 流量统计未接入（`display interface` 有分页，需单独处理）
- 未适配 AC 集中管理场景（`display ap all` 字段可能不同）

---

## 10. 项目结构

```
huawei_ap/
├── custom_components/huawei_ap/
│   ├── __init__.py          # 入口、加载/卸载
│   ├── config_flow.py       # 配置流 + 重新配置 + 选项
│   ├── coordinator.py       # 轮询调度
│   ├── ssh_client.py        # SSH/PTY 传输、命令批量执行、PTY 怪癖处理
│   ├── parser.py            # CLI 输出解析（25 字段实测验证）
│   ├── entity.py            # 实体基类、DeviceInfo
│   ├── sensor.py            # 12 个传感器
│   ├── binary_sensor.py     # 4 个二进制传感器
│   ├── device_tracker.py    # 终端追踪
│   ├── button.py            # 重启按钮
│   ├── const.py             # 常量、命令表、数据模型
│   ├── manifest.json
│   ├── strings.json
│   └── translations/
├── tools/probe_huawei_ap.sh # 零依赖诊断脚本
└── README.md
```

---

## 附录：Web 协议逆向记录

虽然最终没采用，但这套协议对同系列设备仍有参考价值。全部结论来自设备自带前端代码（`/service/login.js`、`/util/ajax.js`，均为 gzip 压缩）。

### 认证

```
POST /login.cgi
UserName=<u>&Password=<p>&LanguageType=0
```

| 结果 | 响应 |
|---|---|
| 成功 | body `0&<pwdAlertTime>` + `Set-Cookie: SessionID=...` |
| 密码错误 | `ErrorMsg=1008` |
| 会话超时 | `ErrorMsg=1016` |
| **登录数已满** | **`ErrorMsg=1012`** |
| 未认证访问 | **HTTP 450 + `Return Login Page`** |

`Set-Cookie` 格式不规范（缺空格），标准 cookie 解析器会失败，需手动正则提取。

### 数据通道

NETCONF 1.0 信封塞进表单，**末尾必须带 `]]>]]>`**，否则设备挂起：

```
htmlID=default&MessageID=1&TimeoutFlag=false&
<rpc message-id="1" xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <get><filter type="subtree">
    <featurename istop="true" type="mib"><sysname/></featurename>
  </filter></get>
</rpc>]]>]]>
```

执行 CLI 则把 `<get>` 换成 `<edit-config operation="merge">` 且 `type="cli"`。

内部 flag 常量：`LOGIN_OR_UPLOAD_FLAG=1`、`CLI_OR_MIB_SET_FLAG=2`、`MIB_GET_FLAG=3`、`CLOSE_SESSION_FLAG=4`。

### 保活

```
POST /handshake.cgi    htmlID=default&MessageID=<n>
```

返回含 `1016` 即会话过期。

### 其他探测结论

- `/view/main/default.html?pageid=xxx` 里的 `pageid` 只是前端 `WEB.random(1e6)` 生成的随机数，不是页面标识
- SNMP（161）默认未开启
- 登出接口 `/logout.cgi`、`/disconnect.cgi`、`/logoff.cgi` 存在但需要特定参数

---

## 许可

MIT
