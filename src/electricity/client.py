"""长安大学站点常量与请求 UA。

站点入口在微信 H5 里跑，因此请求需要带 MicroMessenger UA；
这与「微信 OAuth 登录」无关，只是服务端的浏览器识别。
"""

from __future__ import annotations

from .changan import AREA_ID, AREA_NAME, CAMPUS_ROOT

# 微信 Android 内置浏览器典型 UA（含 MicroMessenger）
WECHAT_UA = (
    "Mozilla/5.0 (Linux; Android 12; M2012K11AC Build/SKQ1.211006.001; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/107.0.5304.141 "
    "Mobile Safari/537.36 XWEB/5169 MMWEBSDK/20220903 MMWEBID/3905 "
    "MicroMessenger/8.0.28.2240(0x28001C35) WeChat/arm64 Weixin "
    "NetType/WIFI Language/zh_CN ABI/arm64"
)

DEFAULT_BASE = "http://bd.bdfairy.cn"

# 长安大学固定校区参数（保留别名，方便旧代码迁移）
DEFAULT_AREA_ID = AREA_ID
DEFAULT_AREA_NAME = AREA_NAME
DEFAULT_CAMPUS_ROOT = CAMPUS_ROOT
