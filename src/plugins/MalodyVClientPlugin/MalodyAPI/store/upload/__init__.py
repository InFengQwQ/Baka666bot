"""谱面上传完整流程 (签名→OSS→发布)"""
import os
import hashlib
import time
import requests
from src.storage import plugin_data
from ...core import MALODY_VERSION, STORE_API, DEFAULT_TIMEOUT

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CACHE_DIR = str(plugin_data("MalodyVClientPlugin") / "upload_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

HEADERS_UPLOAD = {
    "User-Agent": f"Malody {MALODY_VERSION}",
    "Malody": MALODY_VERSION,
    "Content-Type": "application/x-www-form-urlencoded",
}


def upload_chart(uid: str, store_token: str, sid: str, cid: str, chart_path: str, files: list, api_base: str = "http://api.paimonnokoya.me", timeout: int = 30) -> tuple:
    hash_list = []
    name_list = []
    size_list = []
    for fname in files:
        fpath = os.path.join(chart_path, fname)
        if not os.path.exists(fpath):
            return False, f"文件不存在: {fpath}"
        with open(fpath, "rb") as f:
            data = f.read()
        hash_list.append(hashlib.md5(data).hexdigest())
        name_list.append(fname)
        size_list.append(len(data))
    name_str = ",".join(name_list)
    hash_str = ",".join(hash_list)

    t = str(int(time.time()))
    sign_url = f"{api_base}/api/store/upload/sign?api={STORE_API}&uid={uid}&key={store_token}&t={t}"
    sign_data = {"sid": sid, "cid": cid, "name": name_str, "hash": hash_str}
    try:
        resp = requests.post(sign_url, data=sign_data, headers=HEADERS_UPLOAD, timeout=timeout, verify=False)
    except Exception as e:
        return False, f"签名请求失败: 请反馈bot主人"
    cache_file = os.path.join(CACHE_DIR, f"sign_{sid}_{cid}.json")
    with open(cache_file, "w", encoding="utf-8") as f:
        f.write(resp.text)
    sign_result = resp.json()
    if sign_result.get("code") != 0:
        return False, f"签名失败: {sign_result}"
    oss_info = sign_result.get("data")
    if not oss_info:
        return False, "签名响应缺少 OSS 信息"

    oss_url = oss_info["host"]
    oss_dir = oss_info["dir"]
    access_id = oss_info["accessid"]
    policy = oss_info["policy"]
    signature = oss_info["signature"]
    for fname, fsize in zip(files, size_list):
        fpath = os.path.join(chart_path, fname)
        with open(fpath, "rb") as f:
            file_data = f.read()
        key = f"{oss_dir}{fname}"
        multipart_data = {"key": key, "policy": policy, "OSSAccessKeyId": access_id, "signature": signature}
        files_payload = {"file": (fname, file_data)}
        try:
            oss_resp = requests.post(oss_url, data=multipart_data, files=files_payload, timeout=timeout, verify=False)
        except Exception as e:
            return False, f"OSS 上传失败 ({fname}): 请反馈bot主人"
        if oss_resp.status_code not in (200, 204):
            return False, f"OSS 上传错误 ({fname}): {oss_resp.status_code} {oss_resp.text}"

    finish_url = f"{api_base}/api/store/upload/finish"
    finish_data = {"sid": sid, "cid": cid, "api": str(STORE_API), "uid": uid, "key": store_token, "t": str(int(time.time()))}
    try:
        finish_resp = requests.post(finish_url, data=finish_data, headers=HEADERS_UPLOAD, timeout=timeout, verify=False)
    except Exception as e:
        return False, f"发布完成请求失败: 请反馈bot主人"
    finish_result = finish_resp.json()
    if finish_result.get("code") == 0:
        return True, f"上传成功！谱面已发布。\n详情: {finish_result}"
    else:
        return False, f"发布完成接口返回错误: {finish_result}"


