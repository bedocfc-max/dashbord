import sys
import os
import logging
import time
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementNotInteractableException,
    StaleElementReferenceException,
)


# =========================
# Helper: Get base path
# =========================
def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = get_base_path()
TIMEOUT = 40


# =========================
# Ensure logs directory exists
# =========================
logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(logs_dir, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(logs_dir, 'app.log'),
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


# =========================
# Get msedgedriver path
# =========================
def get_driver_path():
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        driver_path = os.path.join(exe_dir, "msedgedriver.exe")
        if os.path.exists(driver_path):
            return driver_path

    driver_path = os.path.join(BASE_PATH, "msedgedriver.exe")
    if os.path.exists(driver_path):
        return driver_path

    raise FileNotFoundError("msedgedriver.exe not found.")


# =========================
# Helper: Wait and Click
# =========================
def wait_and_click(wait, locator, step_name, retries=3):
    """Wait for element to be clickable and click it with retry on stale reference."""
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            element = wait.until(EC.element_to_be_clickable(locator))
            element.click()
            logging.info(f"Step '{step_name}' - clicked successfully (attempt {attempt})")
            return
        except StaleElementReferenceException as e:
            last_error = e
            logging.warning(
                f"Step '{step_name}' - stale element on attempt {attempt}/{retries}, retrying..."
            )
            time.sleep(1)
        except TimeoutException:
            raise Exception(
                f"فشل في الخطوة '{step_name}' — "
                f"العنصر غير موجود أو غير قابل للضغط بعد {TIMEOUT} ثانية "
                f"[selector: {locator[1]}]"
            )
        except ElementNotInteractableException:
            raise Exception(
                f"فشل في الخطوة '{step_name}' — "
                f"العنصر موجود لكنه غير قابل للتفاعل [selector: {locator[1]}]"
            )
        except Exception as e:
            raise Exception(f"فشل في الخطوة '{step_name}' — خطأ غير متوقع: {str(e)}")
    raise Exception(
        f"فشل في الخطوة '{step_name}' — "
        f"العنصر أصبح قديماً (stale) بعد {retries} محاولات [selector: {locator[1]}]"
    )


# =========================
# Helper: Wait and Type
# =========================
def wait_and_type(wait, locator, text, step_name):
    """Wait for input element and type text with descriptive error."""
    try:
        element = wait.until(EC.presence_of_element_located(locator))
        element.clear()
        element.send_keys(text)
        logging.info(f"Step '{step_name}' - text entered successfully")
    except TimeoutException:
        raise Exception(
            f"فشل في الخطوة '{step_name}' — "
            f"حقل الإدخال غير موجود بعد {TIMEOUT} ثانية "
            f"[selector: {locator[1]}]"
        )
    except Exception as e:
        raise Exception(f"فشل في الخطوة '{step_name}' — خطأ غير متوقع: {str(e)}")


# =========================
# Helper: Handle Alert
# =========================
def handle_alert(driver, step_name, action='accept'):
    """Wait for a JS alert and accept/dismiss it with descriptive error."""
    try:
        alert = WebDriverWait(driver, TIMEOUT).until(EC.alert_is_present())
        alert_text = alert.text
        logging.info(f"Step '{step_name}' - alert text: {alert_text}")
        if action == 'accept':
            alert.accept()
        else:
            alert.dismiss()
        logging.info(f"Step '{step_name}' - alert handled ({action})")
        return alert_text
    except TimeoutException:
        raise Exception(
            f"فشل في الخطوة '{step_name}' — "
            f"لم يظهر أي alert بعد {TIMEOUT} ثانية"
        )
    except Exception as e:
        raise Exception(f"فشل في الخطوة '{step_name}' — خطأ في التعامل مع alert: {str(e)}")


# =========================
# Phase 1: Login + Navigate + Click OTP + Send OTP
# Returns dict with driver reference on success (waiting_for_otp)
# =========================
def run_automation_phase1(username, password):
    start_time = time.time()
    logging.info(f"Phase 1 starting for user: {username}")

    options = EdgeOptions()
    options.use_chromium = True
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = None

    try:
        driver_path = get_driver_path()
        service = Service(executable_path=driver_path)

        driver = webdriver.Edge(service=service, options=options)
        wait = WebDriverWait(driver, TIMEOUT)

        # ---- Login ----
        driver.get("https://siebel-lb/siebel/app/ecomm_ad/enu")

        wait_and_type(wait, (By.ID, "s_swepi_1"), username, "إدخال اسم المستخدم")
        wait_and_type(wait, (By.ID, "s_swepi_2"), password, "إدخال كلمة المرور")
        wait_and_click(wait, (By.ID, "s_swepi_22"), "الضغط على زر تسجيل الدخول")

        logging.info("Login button clicked")
        time.sleep(2)

        # Check for login error banner
        error_elements = driver.find_elements(By.ID, "statusBar")
        if error_elements:
            error_text = error_elements[0].text.strip()
            if error_text:
                raise Exception(f"فشل تسجيل الدخول: {error_text}")

        try:
            wait.until(EC.invisibility_of_element_located((By.ID, "s_swepi_1")))
        except TimeoutException:
            raise Exception(
                "فشل تسجيل الدخول — شاشة الدخول لم تختفِ خلال "
                f"{TIMEOUT} ثانية. تحقق من بيانات الدخول."
            )

        logging.info("Login successful")

        # ---- Navigate to Service Request view ----
        driver.get(
            "https://siebel-lb/siebel/app/ecomm_ad/enu"
            "?SWECmd=GotoView"
            "&SWEView=VFCC+All+Service+Request+across+Organizations"
            "&SWERF=1&SWEHo=&SWEBU=1"
        )
        logging.info("Navigated to Service Request view")

        # Wait for the page to fully load and stabilise before interacting
        try:
            wait.until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            pass
        # Extra settle time for Siebel's dynamic DOM to finish rendering
        time.sleep(3)

        # ---- Click OTP button ----
        wait_and_click(wait, (By.NAME, "s_1_1_0_0"), "الضغط على زر OTP")

        # ---- Click Send OTP button ----
        wait_and_click(wait, (By.NAME, "s_3_1_93_0"), "الضغط على زر Send OTP")

        execution_time = f"{time.time() - start_time:.2f} seconds"
        logging.info("Phase 1 complete — waiting for OTP input from user")

        return {
            "status": "waiting_for_otp",
            "message": "تم إرسال OTP إلى هاتفك. الرجاء إدخال الكود.",
            "data": "",
            "execution_time": execution_time,
            "driver": driver,
            "start_time": start_time
        }

    except Exception as e:
        execution_time = f"{time.time() - start_time:.2f} seconds"
        logging.exception("Phase 1 failed")
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        return {
            "status": "error",
            "message": str(e),
            "data": "",
            "execution_time": execution_time
        }


# =========================
# Phase 2: New → Enter OTP → Verify → Handle Alerts → Close Popup
# =========================
def run_automation_phase2(driver, otp_code, start_time):
    wait = WebDriverWait(driver, TIMEOUT)
    try:
        # ---- Click New ----
        wait_and_click(wait, (By.NAME, "s_3_1_6_0"), "الضغط على زر New")

        # ---- Enter OTP ----
        wait_and_type(wait, (By.NAME, "s_3_1_92_0"), otp_code, "إدخال كود OTP")

        # ---- Click Verify OTP ----
        wait_and_click(wait, (By.NAME, "s_3_1_97_0"), "الضغط على زر Verify OTP")

        # ---- Handle first alert: "Thanks for your verification" ----
        handle_alert(driver, "تأكيد التحقق من OTP")

        # ---- Close popup ----
        wait_and_click(
            wait,
            (By.CSS_SELECTOR, "button.ui-dialog-titlebar-close"),
            "إغلاق النافذة المنبثقة"
        )

        # ---- Handle second alert: "Click OK to discard unsaved data" ----
        handle_alert(driver, "تأكيد إغلاق النافذة")

        execution_time = f"{time.time() - start_time:.2f} seconds"
        logging.info("Phase 2 complete — OTP verified successfully")

        return {
            "status": "success",
            "message": "تم التحقق من OTP بنجاح وإغلاق النافذة",
            "data": "اكتملت عملية OTP",
            "execution_time": execution_time
        }

    except Exception as e:
        execution_time = f"{time.time() - start_time:.2f} seconds"
        logging.exception("Phase 2 failed")
        return {
            "status": "error",
            "message": str(e),
            "data": "",
            "execution_time": execution_time
        }

    finally:
        try:
            driver.quit()
        except Exception:
            pass
        logging.info("WebDriver closed after phase 2")