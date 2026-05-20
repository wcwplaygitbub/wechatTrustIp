import os
import tempfile
import time

import bcrypt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response, JSONResponse
from itsdangerous import Signer, BadSignature
from starlette.templating import Jinja2Templates

from app.config import settings
from app.log_buffer import log_buffer

router = APIRouter(prefix="/console")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Cookie 认证
_signer = Signer(settings.console_secret_key)
_COOKIE_NAME = "console_token"
_COOKIE_MAX_AGE = 86400  # 24 小时


def _make_token(username: str) -> str:
    payload = f"{username}:{int(time.time())}"
    return _signer.sign(payload).decode()


def _verify_token(token: str) -> bool:
    try:
        payload = _signer.unsign(token).decode()
        _, ts = payload.rsplit(":", 1)
        return int(ts) > time.time() - _COOKIE_MAX_AGE
    except (BadSignature, ValueError):
        return False


def _get_current_user(request: Request) -> str | None:
    token = request.cookies.get(_COOKIE_NAME)
    if not token or not _verify_token(token):
        return None
    try:
        payload = _signer.unsign(token).decode()
        return payload.rsplit(":", 1)[0]
    except (BadSignature, ValueError):
        return None


class AuthRequired(Exception):
    pass


def require_login(request: Request) -> str:
    user = _get_current_user(request)
    if user:
        return user
    raise AuthRequired()


def register_auth_handler(app):
    from fastapi import FastAPI
    @app.exception_handler(AuthRequired)
    async def auth_exception_handler(request: Request, exc: AuthRequired):
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(url="/console/login", status_code=303)
        return JSONResponse(status_code=401, content={"detail": "未登录"})


def _get_stored_hash() -> str | None:
    try:
        with open(settings.password_hash_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def _set_stored_hash(pw_hash: str):
    tmp = settings.password_hash_file + ".tmp"
    with open(tmp, "w") as f:
        f.write(pw_hash)
    os.replace(tmp, settings.password_hash_file)


def _verify_password(password: str) -> bool:
    stored = _get_stored_hash()
    if stored:
        return bcrypt.checkpw(password.encode(), stored.encode())
    return password == settings.console_password


# ---- 路由 ----


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": ""})


@router.post("/login")
async def login_post(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    if username != settings.console_username or not _verify_password(password):
        return templates.TemplateResponse("login.html", {
            "request": request, "error": "用户名或密码错误", "username": username
        })

    token = _make_token(username)
    response = RedirectResponse(url="/console/", status_code=303)
    response.set_cookie(_COOKIE_NAME, token, max_age=_COOKIE_MAX_AGE, httponly=True)
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/console/login", status_code=303)
    response.delete_cookie(_COOKIE_NAME)
    return response


@router.get("/", response_class=HTMLResponse)
def index(request: Request, user: str = Depends(require_login)):
    import time as _time

    scheduler = request.app.state.scheduler
    ip_checker = request.app.state.ip_checker
    event_store = request.app.state.event_store
    started_at = request.app.state.started_at

    registered_ip = ip_checker.load_ip()
    current_ip = scheduler.last_ip or registered_ip
    ip_match = registered_ip is not None and current_ip is not None and registered_ip == current_ip
    has_cookie = os.path.exists(settings.cookie_file)
    next_run = scheduler.get_next_check_time() or "未知"

    qrcode_file = os.path.join(settings.data_dir, "qrcode.png")
    has_qrcode = not has_cookie and os.path.exists(qrcode_file)

    # D1 + D3: 服务端渲染初始值
    last_update_time = event_store.get_last_update_time()
    uptime_seconds = int(_time.time() - started_at)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    uptime = f"{days}天{hours}小时{minutes}分钟" if days > 0 else f"{hours}小时{minutes}分钟"

    return templates.TemplateResponse("index.html", {
        "request": request,
        "registered_ip": registered_ip,
        "current_ip": current_ip,
        "ip_match": ip_match,
        "has_cookie": has_cookie,
        "app_ids": settings.wework_app_ids,
        "next_run": next_run,
        "has_qrcode": has_qrcode,
        "last_update_time": last_update_time,
        "uptime": uptime,
        "recent_events": event_store.get_events(limit=5),
        "app_statuses": list(event_store.get_app_statuses().values()),
        "toast": "",
        "toast_type": "success",
    })


@router.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request, user: str = Depends(require_login)):
    data = log_buffer.get_entries(page=1, page_size=50)
    return templates.TemplateResponse("logs.html", {
        "request": request,
        "entries": data["entries"],
        "total": data["total"],
        "page": data["page"],
        "page_size": data["page_size"],
    })


@router.get("/logs-json")
def logs_json(user: str = Depends(require_login), after: float = 0,
              level: str = "ALL", page: int = 1, page_size: int = 50):
    """分页日志接口"""
    return log_buffer.get_entries(
        after=after,
        level=level if level != "ALL" else None,
        page=max(1, page),
        page_size=min(100, max(10, page_size)),
    )


@router.get("/qrcode")
def qrcode_image(user: str = Depends(require_login)):
    qrcode_file = os.path.join(settings.data_dir, "qrcode.png")
    if os.path.exists(qrcode_file):
        return FileResponse(qrcode_file, media_type="image/png")
    return Response(status_code=404)


@router.post("/clear-logs")
def clear_logs(user: str = Depends(require_login)):
    log_buffer.clear()
    return {"ok": True, "message": "日志已清除"}


@router.get("/config", response_class=HTMLResponse)
def config_page(request: Request, user: str = Depends(require_login)):
    return templates.TemplateResponse("config.html", {
        "request": request,
        "config": settings,
        "toast": "",
        "toast_type": "success",
    })


@router.post("/config")
async def config_update(request: Request, user: str = Depends(require_login)):
    form = await request.form()
    scheduler = request.app.state.scheduler
    toast = ""
    toast_type = "success"

    try:
        new_cron = form.get("ip_check_cron", "").strip()
        if new_cron and new_cron != settings.ip_check_cron:
            settings.ip_check_cron = new_cron
            scheduler.reschedule_check(new_cron)
            toast += "Cron 已更新. "

        new_ids = form.get("app_ids", "").strip()
        if new_ids:
            ids = [x.strip() for x in new_ids.split(",") if x.strip()]
            if ids != settings.wework_app_ids:
                settings.wework_app_ids = ids
                scheduler.app_ids = ids
                toast += "应用 ID 已更新. "

        if not toast:
            toast = "无变更"
            toast_type = "info"

    except Exception as e:
        toast = f"更新失败: {e}"
        toast_type = "error"

    return templates.TemplateResponse("config.html", {
        "request": request,
        "config": settings,
        "toast": toast,
        "toast_type": toast_type,
    })


@router.get("/password", response_class=HTMLResponse)
def password_page(request: Request, user: str = Depends(require_login)):
    return templates.TemplateResponse("password.html", {
        "request": request, "error": "", "success": "",
    })


@router.post("/password")
async def password_update(request: Request, user: str = Depends(require_login)):
    form = await request.form()
    old_password = form.get("old_password", "")
    new_password = form.get("new_password", "")
    confirm_password = form.get("confirm_password", "")

    if not _verify_password(old_password):
        return templates.TemplateResponse("password.html", {
            "request": request, "error": "当前密码错误", "success": "",
        })

    if new_password != confirm_password:
        return templates.TemplateResponse("password.html", {
            "request": request, "error": "两次输入的新密码不一致", "success": "",
        })

    if len(new_password) < 6:
        return templates.TemplateResponse("password.html", {
            "request": request, "error": "新密码至少 6 位", "success": "",
        })

    pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    _set_stored_hash(pw_hash)

    return templates.TemplateResponse("password.html", {
        "request": request, "error": "", "success": "密码已修改，下次登录生效",
    })


@router.post("/trigger-check")
def trigger_check(request: Request, user: str = Depends(require_login)):
    event_store = request.app.state.event_store
    try:
        event_store.add("user_action", "手动触发 IP 检测", "info")
        request.app.state.scheduler.submit_check()
        return {"ok": True, "message": "IP 检测任务已提交"}
    except Exception as e:
        event_store.add("user_action", f"触发 IP 检测失败: {e}", "error")
        return {"ok": False, "message": f"提交失败: {e}"}


@router.post("/force-update")
def force_update(request: Request, user: str = Depends(require_login)):
    event_store = request.app.state.event_store
    try:
        event_store.add("user_action", "手动强制更新 IP", "info")
        request.app.state.scheduler.submit_force_update()
        return {"ok": True, "message": "强制更新任务已提交"}
    except Exception as e:
        event_store.add("user_action", f"强制更新失败: {e}", "error")
        return {"ok": False, "message": f"提交失败: {e}"}


@router.post("/clear-cookies")
def clear_cookies(request: Request, user: str = Depends(require_login)):
    event_store = request.app.state.event_store
    try:
        if os.path.exists(settings.cookie_file):
            os.remove(settings.cookie_file)
        event_store.add("user_action", "手动清除 Cookie", "warning")
        return {"ok": True, "message": "Cookie 已清除"}
    except Exception as e:
        event_store.add("user_action", f"清除 Cookie 失败: {e}", "error")
        return {"ok": False, "message": f"清除失败: {e}"}


@router.get("/captcha-status")
def captcha_status(user: str = Depends(require_login)):
    captcha_flag = os.path.join(settings.data_dir, "captcha_needed.txt")
    return {"needed": os.path.exists(captcha_flag)}


@router.post("/submit-captcha")
async def submit_captcha(request: Request, user: str = Depends(require_login)):
    form = await request.form()
    code = form.get("captcha_code", "").strip()
    if not code:
        return {"ok": False, "message": "验证码不能为空"}

    captcha_file = os.path.join(settings.data_dir, "captcha_code.txt")
    with open(captcha_file, "w") as f:
        f.write(code)

    return {"ok": True, "message": "验证码已提交"}


@router.get("/status")
def console_status(request: Request, user: str = Depends(require_login)):
    """统一状态轮询接口，供前端定时刷新"""
    import time as _time

    scheduler = request.app.state.scheduler
    ip_checker = request.app.state.ip_checker
    event_store = request.app.state.event_store
    started_at = request.app.state.started_at

    registered_ip = ip_checker.load_ip()
    current_ip = scheduler.last_ip or registered_ip
    has_cookie = os.path.exists(settings.cookie_file)
    qrcode_file = os.path.join(settings.data_dir, "qrcode.png")
    captcha_flag = os.path.join(settings.data_dir, "captcha_needed.txt")

    # D1: 上次成功更新时间
    last_update_time = event_store.get_last_update_time()

    # D3: 服务运行时长
    uptime_seconds = int(_time.time() - started_at)
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    uptime_str = f"{days}天{hours}小时{minutes}分钟" if days > 0 else f"{hours}小时{minutes}分钟"

    # D4: 每个 App 的更新状态
    app_statuses = event_store.get_app_statuses()

    # D5: 最近事件（5条）
    recent_events = event_store.get_events(limit=5)

    return {
        "current_ip": current_ip,
        "registered_ip": registered_ip,
        "ip_match": registered_ip is not None and current_ip is not None and registered_ip == current_ip,
        "has_cookie": has_cookie,
        "has_qrcode": os.path.exists(qrcode_file),
        "next_run": scheduler.get_next_check_time(),
        "captcha_needed": os.path.exists(captcha_flag),
        "app_ids": settings.wework_app_ids,
        "last_update_time": last_update_time,
        "uptime": uptime_str,
        "app_statuses": list(app_statuses.values()),
        "recent_events": recent_events,
    }
