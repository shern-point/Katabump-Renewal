#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import subprocess
from datetime import date, datetime, timedelta, timezone
import requests

TG_CHAT_ID   = os.environ.get("TG_CHAT_ID") or ""
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""

BASE_URL = "https://dashboard.katabump.com"
RENEWAL_INTERVAL_DAYS = 4
RENEWAL_TIMEZONE = timezone(timedelta(hours=8))

def load_accounts():
    raw = os.environ.get("USERS_JSON", "")
    if not raw:
        email = os.environ.get("KATABUMP_EMAIL", "")
        pwd   = os.environ.get("KATABUMP_PASSWORD", "")
        if email:
            return [{
                "email": email,
                "password": pwd,
                "renewal_date": os.environ.get("KATABUMP_RENEWAL_DATE", ""),
            }]
        print("❌ 未配置 USERS_JSON 或 KATABUMP_EMAIL/KATABUMP_PASSWORD")
        return []
    try:
        users = json.loads(raw)
        accounts = []
        for u in users:
            accounts.append({
                "email": u.get("username") or u.get("email") or "",
                "password": u.get("password") or "",
                "renewal_date": u.get("renewal_date"),
            })
        return [a for a in accounts if a["email"]]
    except Exception as e:
        print(f"❌ USERS_JSON 解析失败: {e}")
        return []


def get_next_renewal_date(renewal_date, today=None):
    """返回不早于今天的最近续期日；未配置日期时返回 None。"""
    if renewal_date is None:
        return None
    error_message = "renewal_date 必须是 YYYY-MM-DD 格式的有效日期"
    if not isinstance(renewal_date, str):
        raise ValueError(error_message)
    value = renewal_date.strip()
    if not value:
        return None
    try:
        anchor = date.fromisoformat(value)
    except ValueError:
        raise ValueError(error_message) from None
    if anchor.isoformat() != value:
        raise ValueError(error_message)
    if today is None:
        today = datetime.now(RENEWAL_TIMEZONE).date()
    elapsed_days = (today - anchor).days
    if elapsed_days <= 0:
        return anchor
    periods = (elapsed_days + RENEWAL_INTERVAL_DAYS - 1) // RENEWAL_INTERVAL_DAYS
    return anchor + timedelta(days=periods * RENEWAL_INTERVAL_DAYS)


ACCOUNTS = load_accounts()
CURRENT_EMAIL = ""

def send_tg_message(status_icon, status_text, time_left=""):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID，跳过 Telegram 推送。")
        return
    local_time = time.gmtime(time.time() + 8 * 3600)
    current_time_str = time.strftime("%Y-%m-%d %H:%M:%S", local_time)
    email = CURRENT_EMAIL
    if '@' in email:
        name, domain = email.split('@', 1)
        if len(name) > 4:
            masked_email = f"{name[:2]}****{name[-2:]}@{domain}"
        else:
            masked_email = f"{name}@{domain}"
    else:
        masked_email = (email[:2] + '****') if email else "未知"
    detail = (time_left or "").strip()
    text = (
        f"🇫🇷 katabump 续期通知\n\n"
        f"{status_icon} {status_text}\n"
        f"👤 续期账户: {masked_email}\n"
        f"⏱️ 续期时间: {current_time_str}"
    )
    if detail:
        text += f"\n📋 详情: {detail}"
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print("📩 Telegram 通知发送成功！")
        else:
            print(f"⚠️ Telegram 通知发送失败: {r.text}")
    except Exception as e:
        print(f"⚠️ Telegram 通知发送异常: {e}")

_EXPAND_JS = """
(function() {
    var ts = document.querySelector('input[name="cf-turnstile-response"]');
    if (!ts) return 'no-turnstile';
    var el = ts;
    for (var i = 0; i < 20; i++) {
        el = el.parentElement;
        if (!el) break;
        var s = window.getComputedStyle(el);
        if (s.overflow === 'hidden' || s.overflowX === 'hidden' || s.overflowY === 'hidden')
            el.style.overflow = 'visible';
        el.style.minWidth = 'max-content';
    }
    document.querySelectorAll('iframe').forEach(function(f){
        if (f.src && f.src.includes('challenges.cloudflare.com')) {
            f.style.width = '300px'; f.style.height = '65px';
            f.style.minWidth = '300px';
            f.style.visibility = 'visible'; f.style.opacity = '1';
        }
    });
    return 'done';
})()
"""

_EXISTS_JS = """
(function(){
    return document.querySelector('input[name="cf-turnstile-response"]') !== null;
})()
"""

_SOLVED_JS = """
(function(){
    var i = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(i && i.value && i.value.length > 20);
})()
"""

_WININFO_JS = """
(function(){
    return {
        sx: window.screenX || 0,
        sy: window.screenY || 0,
        oh: window.outerHeight,
        ih: window.innerHeight
    };
})()
"""

_TURNSTILE_BBOX_JS = """
(function(){
    function expand(f){
        f.style.width='300px'; f.style.height='80px';
        f.style.minWidth='300px'; f.style.minHeight='80px';
        f.style.visibility='visible'; f.style.opacity='1';
        f.style.zIndex='9999';
        var p=f.parentElement, guard=0;
        while(p && guard<14){ p.style.overflow='visible'; p=p.parentElement; guard++; }
        var r=f.getBoundingClientRect();
        return { x: Math.round(r.left), y: Math.round(r.top),
                 w: Math.round(r.width), h: Math.round(r.height) };
    }
    if (!window.frames) return null;
    var frames = document.querySelectorAll('iframe');
    for (var i=0;i<frames.length;i++){
        var f=frames[i]; var src=f.src||'';
        if (src.indexOf('challenges.cloudflare.com')>-1 || src.indexOf('/turnstile/')>-1){
            var r=f.getBoundingClientRect();
            if (r.width>0 && r.height>0) return expand(f);
        }
    }
    var q = document.querySelector(
        '[class*="cf-turnstile"] iframe, [id*="turnstile"] iframe, '+
        '[class*="turnstile"] iframe, .cf-turnstile-wrapper iframe'
    );
    if (q) return expand(q);
    return null;
})()
"""

_IFRAME_MAP_JS = """
(function(){
    var out=[];
    var frames=document.querySelectorAll('iframe');
    for (var i=0;i<frames.length;i++){
        var f=frames[i], r=f.getBoundingClientRect();
        out.push({ src:(f.src||'').slice(0,80),
                   x:Math.round(r.left), y:Math.round(r.top),
                   w:Math.round(r.width), h:Math.round(r.height) });
    }
    return JSON.stringify(out);
})()
"""

def js_fill_input(sb, selector: str, text: str):
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"')
    sb.execute_script(f"""
    (function(){{
        var el = document.querySelector('{selector}');
        if (!el) return;
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
        if (nativeInputValueSetter) {{
            nativeInputValueSetter.call(el, "{safe_text}");
        }} else {{
            el.value = "{safe_text}";
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    }})()
    """)

def _activate_window():
    for cls in ["chrome", "chromium", "Chromium", "Chrome", "google-chrome"]:
        try:
            r = subprocess.run(["xdotool", "search", "--onlyvisible", "--class", cls], capture_output=True, text=True, timeout=3)
            wids = [w for w in r.stdout.strip().split("\n") if w.strip()]
            if wids:
                subprocess.run(["xdotool", "windowactivate", "--sync", wids[0]], timeout=3, stderr=subprocess.DEVNULL)
                time.sleep(0.2)
                return
        except Exception:
            pass
    try:
        subprocess.run(["xdotool", "getactivewindow", "windowactivate"], timeout=3, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def _xdotool_click(x: int, y: int):
    _activate_window()
    try:
        subprocess.run(["xdotool", "mousemove", "--sync", str(x), str(y)], timeout=3, stderr=subprocess.DEVNULL)
        time.sleep(0.15)
        subprocess.run(["xdotool", "click", "1"], timeout=2, stderr=subprocess.DEVNULL)
    except Exception:
        os.system(f"xdotool mousemove {x} {y} click 1 2>/dev/null")

def _get_proxy_rotation():
    """Read the actual selectable nodes from the generated sing-box config."""
    try:
        with open("config.json", encoding="utf-8") as f:
            config = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        print(f"⚠️ 无法读取代理轮换配置: {e}")
        return None

    outbounds = config.get("outbounds", [])
    selector = next((ob for ob in outbounds
                     if ob.get("tag") == "proxy" and ob.get("type") == "selector"), None)
    if selector is None:
        return None
    real_nodes = {ob.get("tag") for ob in outbounds if ob.get("server")
                  and ob.get("type") not in ("direct", "block", "dns", "urltest", "selector")}
    nodes = list(dict.fromkeys(tag for tag in selector.get("outbounds", []) if tag in real_nodes))
    if len(nodes) < 2:
        return None
    controller = config.get("experimental", {}).get("clash_api", {}).get("external_controller")
    if not controller:
        raise ValueError("多节点代理缺少控制接口，请重新运行 proxy_handler.py 生成 config.json")
    return {"nodes": nodes, "api_url": f"http://{controller}", "current_node": None}


def _select_proxy_node(rotation, advance=False):
    """Pin the initial automatic choice, then rotate from the last selected node."""
    nodes = rotation["nodes"]
    current = rotation["current_node"]
    advance = advance and current is not None
    try:
        with requests.Session() as session:
            # The local controller must not inherit HTTP_PROXY / HTTPS_PROXY.
            session.trust_env = False
            if current is None:
                response = session.get(f"{rotation['api_url']}/proxies/proxy", timeout=5)
                response.raise_for_status()
                current = response.json().get("now")
                if current == "auto":
                    response = session.get(f"{rotation['api_url']}/proxies/auto", timeout=5)
                    response.raise_for_status()
                    current = response.json().get("now")
            if current not in nodes:
                raise ValueError("无法确定当前代理节点")
            selected = nodes[(nodes.index(current) + 1) % len(nodes)] if advance else current
            response = session.put(
                f"{rotation['api_url']}/proxies/proxy", json={"name": selected}, timeout=5,
            )
            response.raise_for_status()
        # Only advance after a confirmed switch; failed requests retry the same node.
        rotation["current_node"] = selected
        if advance:
            print(f"🔄 切换代理节点: {current} -> {selected}")
        else:
            print(f"🔗 固定本次续期代理节点: {selected}")
        return True
    except (requests.RequestException, ValueError, AttributeError) as e:
        print(f"❌ 代理节点选择失败，本次不启动账号浏览器: {e}")
        return False


def _restart_proxy():
    if not os.path.exists("sing-box"):
        print("  （本环境无 sing-box 可执行文件，跳过代理节点切换）")
        return
    print("\n🔄 重启 sing-box 以切换代理节点...")
    subprocess.run(["pkill", "-9", "-f", "sing-box"], capture_output=True)
    time.sleep(2)
    log = open("singbox.log", "ab")
    try:
        subprocess.Popen(
            ["./sing-box", "run", "-c", "config.json"],
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
    finally:
        log.close()
    time.sleep(26)
    try:
        with open("singbox.log", "rb") as f:
            lines = f.read().decode("utf-8", "ignore").splitlines()
        shown = 0
        for ln in lines[-40:]:
            if ("urltest" in ln or "selected" in ln or "node-" in ln) and shown < 5:
                print("   sing-box:", ln.strip())
                shown += 1
    except Exception:
        pass

def _switch_to_turnstile_frame(sb):
    try:
        el = sb.driver.execute_script("""
        (function(){
            var frames = document.querySelectorAll('iframe');
            for (var i = 0; i < frames.length; i++){
                var f = frames[i], s = f.src || '';
                if (s.indexOf('challenges.cloudflare.com') > -1 ||
                    s.indexOf('turnstile') > -1) return f;
            }
            var q = document.querySelector(
                '[class*="cf-turnstile"], [id*="turnstile"]');
            if (q){ var qf = q.querySelector('iframe'); if (qf) return qf; }
            return null;
        })()
        """)
        if el is None:
            return False
        sb.driver.switch_to.frame(el)
        return True
    except Exception:
        return False

def handle_turnstile(sb) -> bool:
    print("🔍 处理 Cloudflare Turnstile 验证...")
    time.sleep(2)
    if sb.execute_script(_SOLVED_JS):
        print("✅ 已静默通过")
        return True
    try:
        fm = sb.execute_script(_IFRAME_MAP_JS)
        print(f"  📄 页面 iframe: {fm}")
    except Exception:
        pass
    for _ in range(3):
        try: sb.execute_script(_EXPAND_JS)
        except Exception: pass
        time.sleep(0.5)
    for attempt in range(4):
        if sb.execute_script(_SOLVED_JS):
            print(f"✅ Turnstile 通过（A 第 {attempt + 1} 次）")
            return True
        print(f"🖱️ [A] 第 {attempt + 1}/4 次调用 uc_gui_click_captcha...")
        try:
            if attempt < 2:
                sb.uc_gui_click_captcha()
            else:
                sb.uc_gui_click_cf(frame="iframe", retry=True, blind=True)
        except Exception as e:
            print(f"⚠️ [A] 调用异常: {e}")
        solved = False
        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                solved = True
                break
        if solved:
            print(f"✅ Turnstile 通过（A 第 {attempt + 1} 次）")
            return True
    for attempt in range(4):
        if sb.execute_script(_SOLVED_JS):
            print("✅ Turnstile 通过（B 前缀检查）")
            return True
        bbox = None
        try:
            bbox = sb.execute_script(_TURNSTILE_BBOX_JS)
        except Exception:
            bbox = None
        if not bbox:
            print("⚠️ [B] 未定位到 Turnstile iframe，稍等重试...")
            time.sleep(2)
            continue
        try:
            wi = sb.execute_script(_WININFO_JS)
        except Exception:
            wi = {"sx": 0, "sy": 0, "oh": 800, "ih": 768}
        bar = wi.get("oh", 800) - wi.get("ih", 768)
        cx = bbox["x"] + wi.get("sx", 0) + 30
        cy = bbox["y"] + wi.get("sy", 0) + bar + max(28, int(bbox["h"]) // 2)
        print(f"🖱️ [B] xdotool 点击复选框 ({cx}, {cy})  bbox={bbox}")
        _xdotool_click(cx, cy)
        solved = False
        for _ in range(8):
            time.sleep(0.5)
            if sb.execute_script(_SOLVED_JS):
                solved = True
                break
        if solved:
            print(f"✅ Turnstile 通过（B 第 {attempt + 1} 次）")
            return True
        print(f"  ⚠️ [B] 第 {attempt + 1} 次未通过")
    for attempt in range(3):
        if sb.execute_script(_SOLVED_JS):
            print("✅ Turnstile 通过（C 前缀检查）")
            return True
        print(f"🖱️ [C] 第 {attempt + 1}/3 切入 iframe 尝试...")
        if not _switch_to_turnstile_frame(sb):
            print("  ⚠️ [C] 未找到 Turnstile iframe")
            sb.driver.switch_to.default_content()
            time.sleep(2)
            continue
        try:
            cb = sb.driver.execute_script("""
            (function(){
                var cands = document.querySelectorAll(
                    '[role="checkbox"], input[type="checkbox"],'+
                    '[class*="checkbox"], [class*="btn-check"]'
                );
                for (var i = 0; i < cands.length; i++){
                    var e = cands[i]; var r = e.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) return e;
                }
                return null;
            })()
            """)
            if cb is not None:
                sb.driver.execute_script("arguments[0].focus(); arguments[0].click();", cb)
                print("    [C] 已 click 复选框元素")
            else:
                sb.driver.switch_to.active_element.send_keys(" ")
                print("    [C] 未找到复选框元素，发送空格键")
        except Exception as e:
            print(f"    ⚠️ [C] 异常: {e}")
        finally:
            sb.driver.switch_to.default_content()
        solved = False
        for _ in range(6):
            time.sleep(1)
            if sb.execute_script(_SOLVED_JS):
                solved = True
                break
        if solved:
            print(f"✅ Turnstile 通过（C 第 {attempt + 1} 次）")
            return True
    print("  ❌ Turnstile A/B/C 策略均失败")
    return False

def login(sb, email, password) -> bool:
    print(f"🌐 打开登录页面: {BASE_URL}/auth/login")
    sb.uc_open_with_reconnect(BASE_URL + "/auth/login", reconnect_time=8)
    time.sleep(6)
    print("⏳ 等待 Cloudflare 验证通过...")
    cf_passed = False
    for i in range(30):
        page_src = sb.get_page_source() or ""
        if 'input[name="email"]' in page_src.lower() or 'name="email"' in page_src.lower():
            cf_passed = True
            print(f"✅ Cloudflare 验证已通过（{i+1}s）")
            break
        time.sleep(1)
    if not cf_passed:
        print("⚠️ Cloudflare 验证可能未通过，继续尝试...")
    try:
        sb.wait_for_element('input[name="email"]', timeout=15)
    except Exception:
        try:
            sb.wait_for_element('input[name="Email"]', timeout=5)
        except Exception:
            print("❌ 页面未加载出登录表单")
            print(f"  当前 URL: {sb.get_current_url()}")
            print(f"  当前标题: {sb.get_title() or ''}")
            sb.save_screenshot("login_load_fail.png")
            return False
    print("🍪 关闭可能的 Cookie 弹窗...")
    try:
        for btn in sb.find_elements("button"):
            if "Accept" in (btn.text or ""):
                btn.click()
                time.sleep(0.5)
                break
    except Exception:
        pass
    print("📧 填写邮箱...")
    js_fill_input(sb, 'input[name="email"]', email)
    time.sleep(0.3)
    print("🔑 填写密码...")
    js_fill_input(sb, 'input[name="password"]', password)
    time.sleep(1)
    print("⏳ 等待 Turnstile 验证框出现...")
    ts_found = False
    for i in range(10):
        if sb.execute_script(_EXISTS_JS):
            ts_found = True
            print(f"✅ 检测到 Turnstile（{i+1}s）")
            break
        time.sleep(1)
    if ts_found:
        if not handle_turnstile(sb):
            print("❌ 登录界面的 Turnstile 验证失败")
            sb.save_screenshot("login_turnstile_fail.png")
            return False
    else:
        print("ℹ️ 未检测到 Turnstile")
    print("🖱️ 敲击回车提交表单...")
    sb.press_keys('input[name="password"]', '\n')
    print("⏳ 等待登录跳转...")
    for _ in range(12):
        time.sleep(1)
        cur_url = sb.get_current_url().split('?')[0].lower()
        page_title = sb.get_title() or ""
        if cur_url.startswith(f"{BASE_URL}/dashboard") or "dashboard | katabump" in page_title.lower():
            break
    cur_url = sb.get_current_url().split('?')[0].lower()
    page_title = sb.get_title() or ""
    if cur_url.startswith(f"{BASE_URL}/dashboard") or "dashboard | katabump" in page_title.lower():
        print(f"✅ 登录成功！(URL: {sb.get_current_url()}, Title: {page_title})")
        return True
    print(f"❌ 登录失败，页面未跳转到账户页。(URL: {sb.get_current_url()}, Title: {page_title})")
    sb.save_screenshot("login_failed.png")
    return False

def _read_alert(sb):
    try:
        el = sb.find_element("div.alert", timeout=4)
        return (el.text or "").strip()
    except Exception:
        return ""

def _goto_server_detail(sb) -> bool:
    print("\n🖥️  正在进入服务器续期页...")
    time.sleep(5)
    alert_text = _read_alert(sb)
    if alert_text and "can't renew" in alert_text.lower():
        print(f"ℹ️  页面顶部提示: {alert_text}")
        send_tg_message("ℹ️", "⚠️ 未到续期时间", alert_text)
        return False
    see_link = None
    try:
        see_link = sb.find_element('a[href*="/servers/edit?id="]', timeout=10)
        print(f"✅ 找到链接: {see_link.get_attribute('href')}")
    except Exception:
        print("❌ 未找到 /servers/edit?id= 链接")
        sb.save_screenshot("servers_page_fail.png")
        return False
    see_link.click()
    time.sleep(5)
    print(f"📄 当前页面: {sb.get_current_url()}")
    return True

def _open_renew_modal(sb) -> bool:
    print("\n🔄 查找 Renew 按钮...")
    try:
        renew_btn = sb.find_element('button[data-bs-target="#renew-modal"]', timeout=10)
    except Exception:
        try:
            renew_btn = sb.find_element('button.btn.btn-outline-primary', timeout=5)
        except Exception:
            print("  ❌ 未找到 Renew 按钮")
            return False
    sb.execute_script("""
        (function(){
            var btn = document.querySelector('button[data-bs-target="#renew-modal"]')
                     || document.querySelector('button.btn.btn-outline-primary');
            if (btn) btn.scrollIntoView({behavior:'smooth',block:'center'});
        })()
    """)
    time.sleep(0.8)
    renew_btn.click()
    print("🖱️ 已点击 Renew 按钮，等待模态框弹出...")
    time.sleep(3)
    try:
        sb.find_element('div.modal.show', timeout=5)
        print("✅ Renew 模态框已弹出")
        return True
    except Exception:
        print("⚠️ 模态框未弹出")
        return False

def _submit_first_renew(sb):
    """点击模态框内第一次 Renew 按钮"""
    print("🖱️  点击第一次 Renew 按钮...")
    try:
        submit = sb.find_element('div.modal.show button.btn-primary', timeout=5)
        submit.click()
    except Exception:
        sb.execute_script("""
            (function(){
                var m = document.querySelector('div.modal.show');
                if (!m) return;
                var bs = m.querySelectorAll('button');
                for (var i = 0; i < bs.length; i++)
                    if (/renew/i.test(bs[i].textContent)) { bs[i].click(); break; }
            })()
        """)
    time.sleep(3)

def _confirm_second_renew(sb):
    """处理二次确认弹窗：点第二次 Renew，然后等待被动 ALTCHA 自动完成"""
    print("\n🔄 检查是否有二次确认弹窗...")
    alert_text = _read_alert(sb)
    if alert_text and ("changing the server type" in alert_text.lower()
                       or "startup command" in alert_text.lower()):
        print(f"⚠️ 检测到确认弹窗，点击第二次 Renew...")
        clicked = False
        try:
            confirm_btn = sb.find_element('div.modal.show button.btn-primary', timeout=5)
            confirm_btn.click()
            clicked = True
            print("✅ 第二次点击 btn-primary")
        except Exception:
            pass
        if not clicked:
            sb.execute_script("""
                (function(){
                    var m = document.querySelector('div.modal.show') || document.body;
                    var bs = m.querySelectorAll('button');
                    for (var i = 0; i < bs.length; i++){
                        var t = (bs[i].textContent || '').toLowerCase();
                        if (t.includes('renew') || t.includes('confirm') ||
                            t.includes('ok') || t.includes('continue'))
                            { bs[i].click(); break; }
                    }
                })()
            """)
            print("✅ JS 第二次点击确认按钮")
    else:
        print("ℹ️ 无二次确认弹窗，继续等待...")
    print("⏳ 等待 30 秒（被动 ALTCHA 自动验证中）...")
    time.sleep(30)

def _check_renew_result(sb):
    print("\n📋 检查续期结果...")
    alert_text = _read_alert(sb)
    if not alert_text:
        time.sleep(3)
        alert_text = _read_alert(sb)
    if alert_text:
        print(f"📩 页面提示: {alert_text}")
        low = alert_text.lower()
        if "can't renew" in low or "unable" in low:
            send_tg_message("⏳", "未到续期时间", alert_text)
        elif any(kw in low for kw in ("renewed", "success", "extended")):
            send_tg_message("✅", "续期成功", alert_text)
        else:
            send_tg_message("ℹ️", "续期操作已执行", alert_text)
    else:
        print("ℹ️ 未检测到明确的提示框，可能续期操作未生效")
        send_tg_message("ℹ️", "续期操作已执行", "未检测到明确提示")

def renew_server(sb):
    print("\n" + "#" * 25)
    print("  开始自动续期流程")
    print("#" * 25)
    if not _goto_server_detail(sb):
        return
    if not _open_renew_modal(sb):
        return
    _submit_first_renew(sb)
    _confirm_second_renew(sb)
    _check_renew_result(sb)

def _run_account(sb_kwargs, email, pwd) -> bool:
    global CURRENT_EMAIL
    CURRENT_EMAIL = email
    print("🚀 启动浏览器...")
    try:
        from seleniumbase import SB

        with SB(**sb_kwargs) as sb:
            try:
                sb.open("https://api.ip.sb/ip")
                print(f"📍  当前出口IP: {sb.get_text('body')}")
            except Exception:
                pass
            if login(sb, email, pwd):
                renew_server(sb)
                return True
            else:
                print("\n❌ 登录失败，终止该账号续期操作。")
                send_tg_message("❌", "登录失败", "未知")
                return False
    except Exception as e:
        print(f"\n❌ 账号 {email} 处理异常: {e}")
        send_tg_message("❌", f"处理异常: {e}", "未知")
        return False

def main():
    global CURRENT_EMAIL
    print("#" * 25)
    print("   katabump 自动登录续期")
    print("#" * 25)
    if not ACCOUNTS:
        print("❌ 没有可用的账号，退出。")
        raise SystemExit(1)
    today = datetime.now(RENEWAL_TIMEZONE).date()
    print(f"📅 今天: {today.isoformat()}（UTC+8），续期周期: {RENEWAL_INTERVAL_DAYS} 天")
    pending_accounts = []
    skipped_count = 0
    invalid_count = 0
    for acc in ACCOUNTS:
        try:
            next_date = get_next_renewal_date(acc.get("renewal_date"), today)
        except ValueError as e:
            invalid_count += 1
            print(f"❌ 账号 {acc['email']} 日期配置错误，跳过登录: {e}")
            continue
        if next_date is not None and next_date > today:
            skipped_count += 1
            print(f"⏭️ 账号 {acc['email']} 今天无需续期，跳过登录；下次续期: {next_date.isoformat()}")
            continue
        pending_accounts.append(acc)
        if next_date is None:
            print(f"ℹ️ 账号 {acc['email']} 未配置 renewal_date，按原流程执行")
        else:
            print(f"✅ 账号 {acc['email']} 今天是续期日")
    print(f"👥 共 {len(ACCOUNTS)} 个账号，本次执行 {len(pending_accounts)} 个，"
          f"未到期跳过 {skipped_count} 个，日期配置错误 {invalid_count} 个")
    if not pending_accounts:
        print("ℹ️ 本次没有可执行的账号，跳过浏览器启动。")
        if invalid_count:
            raise SystemExit(1)
        return
    IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
    proxy_str = os.environ.get("PROXY_SERVER", "").strip() or "http://127.0.0.1:8080"
    sb_kwargs = {"uc": True, "headless": False}
    if IS_PROXY:
        print(f"🔗 挂载代理: {proxy_str}")
        sb_kwargs["proxy"] = proxy_str
    else:
        print("🌐 未使用代理，直连访问")
    rotation = _get_proxy_rotation() if IS_PROXY else None
    if rotation:
        print(f"🔄 已启用 {len(rotation['nodes'])} 个代理节点轮换")
    ok_count = 0
    max_attempts = int(os.environ.get("NODE_ATTEMPTS", "3"))
    for idx, acc in enumerate(pending_accounts, 1):
        email = acc["email"]
        pwd   = acc["password"]
        print("\n" + "=" * 25)
        print(f"  处理账号 {idx}/{len(pending_accounts)}: {email}")
        print("=" * 25)
        CURRENT_EMAIL = email
        acc_ok = False
        for attempt in range(1, max_attempts + 1):
            print(f"  ── 节点尝试 {attempt}/{max_attempts} ──")
            if rotation:
                if not _select_proxy_node(rotation, advance=(idx > 1 or attempt > 1)):
                    continue
            elif attempt > 1:
                _restart_proxy()
            if _run_account(sb_kwargs, email, pwd):
                acc_ok = True
                break
        if acc_ok:
            ok_count += 1
        else:
            print(f"❌ 账号 {email} 所有节点尝试均失败")
            send_tg_message("❌", "节点尝试均失败", f"共尝试 {max_attempts} 次")
    print("\n" + "#" * 25)
    print(f"  全部账号处理完毕: {ok_count}/{len(pending_accounts)} 成功，"
          f"{skipped_count} 个未到期跳过，{invalid_count} 个日期配置错误")
    print("#" * 25)
    if ok_count < len(pending_accounts) or invalid_count:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
