import os
import time

import bcrypt
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from itsdangerous import Signer, BadSignature
from starlette.templating import Jinja2Templates

from app.config import settings
from app.log_buffer import log_buffer

router = APIRouter(prefix="/console")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# Cookie 认证
_signer = Signer(settings.wework_webhook_key)
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


def _require_auth(request: Request) -> str | RedirectResponse:
    """返回用户名或重定向到登录页"""
    user = _get_current_user(request)
    if user:
        return user
    return RedirectResponse(url="/console/login", status_code=303)


def _get_stored_hash() -> str | None:
    """读取已保存的密码 hash"""
    try:
        with open(settings.password_hash_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def _set_stored_hash(pw_hash: str):
    with open(settings.password_hash_file, "w") as f:
        f.write(pw_hash)


def _verify_password(password: str) -> bool:
    """验证密码：优先用 hash 文件，否则用 .env 默认密码"""
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
def index(request: Request, toast: str = "", toast_type: str = "success"):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    # 已注册的 IP（上次保存的）
    registered_ip = None
    try:
        with open(settings.ip_file) as f:
            registered_ip = f.read().strip()
    except FileNotFoundError:
        pass

    # 当前公网 IP
    from app.ip_checker import IPChecker
    checker = IPChecker(ip_file=settings.ip_file)
    current_ip = checker.get_current_ip()

    # IP 是否一致
    ip_match = registered_ip is not None and current_ip is not None and registered_ip == current_ip

    has_cookie = os.path.exists(settings.cookie_file)

    # 获取下次执行时间
    next_run = "未知"
    try:
        from app.main import scheduler
        jobs = scheduler._scheduler.get_jobs()
        for job in jobs:
            if "IP 检测" in job.name:
                next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
                break
    except Exception:
        pass

    # 只在 Cookie 不存在时才显示二维码（Cookie 存在说明登录有效，不应该显示旧的二维码）
    qrcode_file = os.path.join(settings.data_dir, "qrcode.png")
    has_qrcode = not has_cookie and os.path.exists(qrcode_file)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "registered_ip": registered_ip,
        "current_ip": current_ip,
        "ip_match": ip_match,
        "has_cookie": has_cookie,
        "app_ids": settings.wework_app_ids,
        "next_run": next_run,
        "has_qrcode": has_qrcode,
        "toast": toast,
        "toast_type": toast_type,
    })


@router.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    qrcode_file = os.path.join(settings.data_dir, "qrcode.png")

    return templates.TemplateResponse("logs.html", {
        "request": request,
        "entries": log_buffer.get_entries(),
        "qrcode_exists": os.path.exists(qrcode_file),
    })


@router.get("/qrcode")
def qrcode_image(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    qrcode_file = os.path.join(settings.data_dir, "qrcode.png")
    if os.path.exists(qrcode_file):
        return FileResponse(qrcode_file, media_type="image/png")
    return Response(status_code=404)


@router.post("/clear-logs")
def clear_logs(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    log_buffer.clear()
    return RedirectResponse(url="/console/logs", status_code=303)


@router.get("/config", response_class=HTMLResponse)
def config_page(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    return templates.TemplateResponse("config.html", {
        "request": request,
        "config": settings,
        "toast": "",
        "toast_type": "success",
    })


@router.post("/config")
async def config_update(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    form = await request.form()
    toast = ""
    toast_type = "success"

    try:
        from app.main import scheduler
        from apscheduler.triggers.cron import CronTrigger

        # 更新 cron
        new_cron = form.get("ip_check_cron", "").strip()
        if new_cron and new_cron != settings.ip_check_cron:
            settings.ip_check_cron = new_cron
            for job in scheduler._scheduler.get_jobs():
                if "IP 检测" in job.name:
                    job.reschedule(trigger=CronTrigger.from_crontab(new_cron))
                    break
            toast += "Cron 已更新. "

        # 更新 app IDs
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
def password_page(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    return templates.TemplateResponse("password.html", {
        "request": request, "error": "", "success": "",
    })


@router.post("/password")
async def password_update(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

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
def trigger_check(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    try:
        from app.main import scheduler
        scheduler._executor.submit(scheduler._check_ip_job)
        return RedirectResponse(url="/console/?toast=IP+检测任务已提交，请查看日志&toast_type=success", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/console/?toast=提交失败: {e}&toast_type=error", status_code=303)


@router.post("/force-update")
def force_update(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    try:
        from app.main import scheduler
        scheduler._executor.submit(scheduler._force_update_job)
        return RedirectResponse(url="/console/?toast=强制更新任务已提交，请查看日志&toast_type=success", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/console/?toast=提交失败: {e}&toast_type=error", status_code=303)


@router.post("/clear-cookies")
def clear_cookies(request: Request):
    auth = _require_auth(request)
    if isinstance(auth, RedirectResponse):
        return auth

    try:
        if os.path.exists(settings.cookie_file):
            os.remove(settings.cookie_file)
        return RedirectResponse(url="/console/?toast=Cookie 已清除&toast_type=success", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/console/?toast=清除失败: {e}&toast_type=error", status_code=303)


@router.get("/captcha-status")
def captcha_status(request: Request):
    """检查是否需要输入验证码"""
    captcha_flag = os.path.join(settings.data_dir, "captcha_needed.txt")
    return {"needed": os.path.exists(captcha_flag)}


@router.post("/submit-captcha")
async def submit_captcha(request: Request):
    """提交验证码"""
    form = await request.form()
    code = form.get("captcha_code", "").strip()
    if not code:
        return RedirectResponse(url="/console/?toast=验证码不能为空&toast_type=error", status_code=303)

    captcha_file = os.path.join(settings.data_dir, "captcha_code.txt")
    with open(captcha_file, "w") as f:
        f.write(code)

    return RedirectResponse(url="/console/?toast=验证码已提交&toast_type=success", status_code=303)
