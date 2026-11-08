from __future__ import annotations

from typing import Any


ENGLISH = {
    # Application and navigation
    "博雅自动助手": "Boya Automation",
    "总览": "Overview",
    "概览与运行控制": "Overview & controls",
    "账号管理": "Accounts",
    "批量账号与登录": "Batch accounts & sign-in",
    "运行设置": "Settings",
    "节奏、模式与自启": "Timing, mode & startup",
    "运行日志": "Logs",
    "查看后台动态": "Background activity",
    "后台未运行": "Background offline",
    "后台运行中": "Background running",
    "后台正在停止": "Stopping background",
    "关闭窗口不会中断后台任务": "Closing this window keeps tasks running",
    # Dashboard
    "登录账号、开始任务，然后让后台安静地处理博雅选课与签到。": (
        "Sign in, start the runner, and let course selection and attendance run quietly."
    ),
    "同步数据": "Sync data",
    "刷新博雅状态": "Refresh Boya status",
    "数据更新时间：{time}": "Data updated: {time}",
    "课程目录更新时间：{time}": "Course catalog updated: {time}",
    "尚未同步": "Not synced yet",
    "已通知后台刷新博雅状态": "Background status refresh requested",
    "让博雅任务安静地完成": "Let Boya tasks run quietly",
    "按账号分别识别缺口，自动选课并处理签到 / 签退。": (
        "Detect each account's category gaps, select courses, and handle check-in / check-out."
    ),
    "开始自动运行": "Start automation",
    "停止后台": "Stop background",
    "●  后台未运行": "●  Background offline",
    "点击左侧按钮开始": "Use the button on the left to start",
    "窗口可关闭 · 后台继续工作": "Close this window · tasks keep running",
    "已启用账号": "Enabled accounts",
    "批量运行": "Batch runner",
    "待补类别": "Needed categories",
    "待选课程": "Courses to select",
    "统计空缺": "Open requirement slots",
    "按统计缺口": "From statistics",
    "已选课程": "Selected courses",
    "跟踪签到签退": "Track check-in / check-out",
    "账号进度": "Account progress",
    "管理账号  ↗": "Manage accounts  ↗",
    "最近动态": "Recent activity",
    # Accounts
    "每个启用账号独立登录、独立统计、独立执行，适合多个账号批量运行。": (
        "Each enabled account signs in, tracks statistics, and runs independently."
    ),
    "添加账号": "Add account",
    "批量模式": "Batch mode",
    "所有标记为“启用”的账号会同时加入后台任务；停用仅暂停该账号。": (
        "Every enabled account joins the background run. Disable an account to pause only that account."
    ),
    "机器只选自主签到；人工选课不退不改。人工和机器选择的自主签到课程都会自动完成定位签到与签退。": (
        "Automation selects autonomous check-in courses only and never changes manual choices. "
        "Both manual and automated autonomous courses receive location check-in and check-out."
    ),
    "账号": "Account",
    "批量状态": "Batch status",
    "校区": "Campus",
    "登录状态": "Sign-in",
    "选择一行账号进行操作": "Select an account to manage it",
    "全部停用": "Disable all",
    "全部启用": "Enable all",
    "删除": "Delete",
    "启用 / 停用": "Enable / disable",
    "查看已选": "View status",
    "账号状态": "Account status",
    "选课来源": "Selection origin",
    "人工 / 机器": "Manual / Auto",
    "总数 · 机器/上限": "Total · Auto / Cap",
    "人工选择": "Manual",
    "机器选择": "Automation",
    "人工 {manual} / 机器 {machine}": "Manual {manual} / Automation {machine}",
    "总 {total} / 机器 {machine_pending} / 上限 {cap}": (
        "Total {total} / Auto {machine_pending} / Cap {cap}"
    ),
    "人工选课 {manual} · 机器选课 {machine} · 自主签到 {autonomous} · 常规签到 {regular}": (
        "Manual {manual} · Automation {machine} · Autonomous {autonomous} · Regular {regular}"
    ),
    "已选课程明细": "Account Status",
    "账号状态 · {username}": "Account status · {username}",
    "课程": "Course",
    "类别": "Category",
    "状态": "Status",
    "签到方式": "Attendance",
    "课程时间": "Course time",
    "考核结果": "Assessment",
    "成绩": "Score",
    "考核通过": "Passed",
    "已选": "Selected",
    "未通过": "Not passed",
    "待考核": "Pending assessment",
    "待公布": "Result pending",
    "当前有 {available} 门符合缺口的自主签到课程可选": (
        "{available} eligible autonomous check-in course(s) are open now"
    ),
    "开放中的缺口课程已满额：{full} 门": (
        "Open courses for required categories are full: {full}"
    ),
    "下一门符合缺口的自主签到课程开放时间：{time}": (
        "Next eligible autonomous course opens: {time}"
    ),
    "当前没有符合缺口且开放的自主签到课程，后台会继续巡检。": (
        "No open autonomous check-in course currently matches the remaining gaps. "
        "The background runner will keep polling."
    ),
    "实时课程目录暂未刷新；自动选课会使用缓存候选逐门实时复核。": (
        "The live course catalog is temporarily unavailable. Auto-selection uses "
        "cached candidates and revalidates each course live before selecting it."
    ),
    "实时课程目录读取中；当前使用缓存候选并逐门复核": (
        "Live catalog pending; cached candidates are being revalidated"
    ),
    "要求": "Required",
    "已通过": "Passed",
    "需选择": "To select",
    "类别要求": "Category requirements",
    "未来开放的自主签到课程": "Upcoming autonomous check-in courses",
    "选课开放": "Selection window",
    "课程开始": "Course starts",
    "余量": "Seats left",
    "暂无符合条件的未来课程": "No upcoming eligible courses",
    "要求已完成": "All requirements completed",
    "还需选 {count} 门": "{count} more course(s) to select",
    "等待考核结果": "Waiting for assessment results",
    "自主签到": "Autonomous check-in",
    "常规签到": "Regular check-in",
    "待结束": "Pending",
    "已结束": "Finished",
    "关闭": "Close",
    "暂无已选课程": "No selected courses",
    "人工选择与机器选择会分别标记；常规签到课程不会由程序修改或签到。": (
        "Manual and automated selections are labeled separately. "
        "The runner never changes or checks in to regular-sign courses."
    ),
    "重新登录": "Sign in again",
    "启用": "Enabled",
    "停用": "Disabled",
    "已登录": "Signed in",
    "需重新登录": "Sign in required",
    "需验证码登录": "Captcha required",
    "登录异常": "Sign-in error",
    "需要重新登录": "Sign-in required",
    "{count} 个账号需要重新登录": "{count} account(s) need to sign in again",
    "{accounts} · 验证码会逐个弹出，完成一个后自动继续下一个": (
        "{accounts} · captcha prompts appear one at a time and the next account continues automatically"
    ),
    "一键登录（{count}）": "Sign in all ({count})",
    "正在登录 {current}/{total}…": "Signing in {current}/{total}…",
    "当前没有需要重新登录的账号": "No accounts currently need to sign in again",
    "有账号正在登录或刷新，请稍后再试": (
        "An account is already signing in or refreshing. Try again shortly."
    ),
    "开始一键登录 {count} 个失效账号，验证码会逐个弹出": (
        "Signing in {count} expired account(s); captcha prompts will appear one at a time"
    ),
    "正在逐个登录失效账号（{current}/{total}）…": (
        "Signing in expired accounts one by one ({current}/{total})…"
    ),
    "正在登录 {current}/{total}：{username}": (
        "Signing in {current}/{total}: {username}"
    ),
    "一键登录完成": "Bulk sign-in complete",
    "成功登录 {success} 个账号，失败 {failed} 个。\n\n失败详情：\n{details}": (
        "Signed in {success} account(s); {failed} failed.\n\nFailure details:\n{details}"
    ),
    "已重新登录全部 {count} 个失效账号": (
        "All {count} expired account(s) signed in again"
    ),
    "{count} 个账号需要重新登录，请使用总览顶部的一键登录": (
        "{count} account(s) need to sign in again. Use “Sign in all” on the Overview page."
    ),
    "账号登录已失效，当前显示的是上次缓存。请点击“重新登录”并完成验证码。": (
        "The account session has expired and cached data is shown. "
        "Choose “Sign in again” and complete the captcha."
    ),
    "等待统计数据": "Waiting for statistics",
    "添加账号后可进行批量操作": "Add an account to use batch actions",
    "共 {count} 个账号": "{count} account(s)",
    "还没有账号，点击右上角“添加账号”": "No accounts yet",
    # Settings
    "调整巡检频率、并发上限和测试模式。保存后后台下一轮生效。": (
        "Adjust polling, pending-course limits, and dry-run mode. Changes apply on the next cycle."
    ),
    "自动化参数": "Automation parameters",
    "巡检间隔（秒）": "Poll interval (seconds)",
    "每次扫描选课与签到窗口的频率，建议 30–120 秒。": (
        "How often to scan selection and attendance windows. 30–120 seconds is recommended."
    ),
    "课程余量刷新（秒）": "Live course refresh (seconds)",
    "直接读取课程开放状态和剩余名额，建议 20–60 秒。": (
        "Read live course availability and remaining seats directly. "
        "20–60 seconds is recommended."
    ),
    "账号状态刷新（秒）": "Account status refresh (seconds)",
    "直接读取已选课程、考核结果和统计，建议 60–300 秒。": (
        "Read selected courses, assessment results, and statistics directly. "
        "60–300 seconds is recommended."
    ),
    "单账号最多已选": "Max selected per account",
    "机器已选且未结束的课程达到上限后暂停抢新课；人工选课不计入且不会被修改。": (
        "Pause new automated selections at this pending-course limit. "
        "Manual selections are never changed or counted against it."
    ),
    "优先类别": "Preferred categories",
    "使用中文逗号或英文逗号分隔，例如：德育, 美育。": (
        "Separate categories with commas, for example: Moral Education, Aesthetic Education."
    ),
    "排除类别": "Excluded categories",
    "这些类别不会自动选，默认为“其他方面”。": (
        "These categories are never selected automatically. Default: Other."
    ),
    "只选仍有未完成要求的类别": "Select only categories with unfinished requirements",
    "关闭后会扩大到所有非排除类别的自主签到课。": (
        "When off, all eligible autonomous check-in courses are considered."
    ),
    "测试模式（只记录决策，不真实操作）": "Dry run (log decisions only)",
    "首次使用建议开启，确认筛选结果后再关闭。": (
        "Recommended for the first run. Turn it off after verifying the filters."
    ),
    "Windows 登录后自动启动后台": "Start background runner after Windows sign-in",
    "无需打开控制台，系统登录后会直接恢复后台巡检。": (
        "Restore the background runner without opening this console."
    ),
    "保存设置": "Save settings",
    "本机与安全": "Local security",
    "密码优先写入 Windows 凭据管理器。": (
        "Passwords are stored in Windows Credential Manager."
    ),
    "配置文件 config.yaml 不包含密码。": "config.yaml never contains passwords.",
    "登录会话和缓存位于用户目录 .autoboya。": (
        "Sessions and caches live in the user's .autoboya directory."
    ),
    "删除账号不会自动删除系统凭据。": (
        "Removing an account does not erase Windows credentials."
    ),
    "打开数据目录": "Open data folder",
    "合规提醒": "Responsible use",
    "自动化可能违反学校规定。请确认课程、签到和出勤要求允许后再使用，避免虚假出勤。": (
        "Automation may violate university rules. Confirm that course selection and "
        "attendance automation are permitted, and never falsify attendance."
    ),
    # Logs and account dialogs
    "显示最近的后台循环、选课、签到和错误记录。": (
        "Recent runner loops, selections, attendance, and errors."
    ),
    "打开日志目录": "Open log folder",
    "刷新日志": "Refresh logs",
    "添加博雅账号": "Add Boya Account",
    "密码只保存在本机系统凭据中，不会写入配置文件。": (
        "Stored in Windows Credential Manager, never in config files."
    ),
    "学号 / 统一身份认证账号": "Student ID / SSO account",
    "统一身份认证密码": "SSO password",
    "显示": "Show",
    "北京": "Beijing",
    "杭州": "Hangzhou",
    "学院路校区": "Xueyuan Road Campus",
    "沙河校区": "Shahe Campus",
    "全部校区": "All Campuses",
    "杭州校区": "Hangzhou Campus",
    "德育": "Moral Education",
    "美育": "Aesthetic Education",
    "劳动教育": "Labor Education",
    "安全健康": "Safety & Health",
    "其他方面": "Other",
    "加入批量自动运行": "Include in batch automation",
    "取消": "Cancel",
    "保存并登录": "Save & sign in",
    "还缺账号": "Account required",
    "请输入学号或统一身份认证账号。": "Enter a student ID or SSO account.",
    "还缺密码": "Password required",
    "请输入统一身份认证密码。": "Enter the SSO password.",
    "输入登录验证码": "Enter Sign-in Captcha",
    "统一身份认证验证码": "SSO captcha",
    "请查看下方图片并填写验证码，完成本次登录。": (
        "Enter the characters shown below to complete sign-in."
    ),
    "验证码图片：{path}": "Captcha image: {path}",
    "继续登录": "Continue sign-in",
    "换一张": "New code",
    # Dynamic status and operations
    "正在停止": "Stopping",
    "正在安全结束当前循环": "Safely finishing the current cycle",
    "PID {pid} · 窗口关闭也不影响任务": "PID {pid} · closing the window keeps tasks running",
    "点击“开始自动运行”启动": "Click “Start automation”",
    "还没有可用账号": "No accounts available",
    "添加账号并登录后，这里会显示各类别完成进度。": (
        "Add and sign in to an account to see category progress here."
    ),
    "添加第一个账号": "Add your first account",
    "要求已齐": "Requirements met",
    "待补 {categories}": "Needed: {categories}",
    "已通过 {passed} 门 · 待考核 {pending} 门": (
        "Passed {passed} · Pending assessment {pending}"
    ),
    "{campus}校区  ·  已选 {selected} 门  ·  校区有效数 {valid}": (
        "{campus} campus  ·  {selected} selected  ·  valid activities: {valid}"
    ),
    "未知": "unknown",
    "暂无动态": "No activity yet",
    "暂无运行日志。登录账号并开始自动运行后，这里会显示实时记录。": (
        "No logs yet. Sign in, start the background runner, and activity will appear here."
    ),
    "先添加账号": "Add an account first",
    "还没有博雅账号。先添加账号并完成登录，再开始自动运行。": (
        "There are no Boya accounts yet. Add and sign in to an account first."
    ),
    "没有启用账号": "No enabled accounts",
    "当前所有账号都已停用，请至少启用一个账号。": (
        "All accounts are disabled. Enable at least one account."
    ),
    "后台已经在运行中": "The background runner is already active",
    "启动失败": "Start failed",
    "已启动批量后台任务，共 {count} 个账号": (
        "Started the batch runner for {count} account(s)"
    ),
    "后台当前没有运行": "The background runner is not active",
    "停止后台任务": "Stop background runner",
    "停止后将不再自动选课、签到或签退。确定停止吗？": (
        "Automatic selection and attendance will stop. Continue?"
    ),
    "正在安全停止后台，请稍候": "Stopping the background runner safely…",
    "更新账号": "Update account",
    "该账号已经存在。是否更新密码和校区并重新登录？": (
        "This account already exists. Update its password and campus and sign in again?"
    ),
    "正在保存凭据并登录，请稍候…": "Saving credentials and signing in…",
    "；系统凭据不可用，已改存本机受保护文件": (
        "; Windows Credential Manager was unavailable, so a protected local file was used"
    ),
    "先选择账号": "Select an account",
    "请先在列表中选择一个账号。": "Select an account from the list first.",
    "该账号正在操作，请稍候": "This account is busy. Please wait.",
    "正在登录 {username}…": "Signing in to {username}…",
    "{username} 已{status}": "{username} is now {status}",
    "已{status}全部账号": "All accounts are now {status}",
    "停用后，这些账号不会参与自动选课和签到。继续吗？": (
        "Disabled accounts will not participate in selection or attendance. Continue?"
    ),
    "删除账号": "Delete account",
    "从程序中删除 {username}？\n\n系统凭据管理器中保存的密码不会被自动清除。": (
        "Remove {username} from this app?\n\nPasswords in Windows Credential Manager are not erased."
    ),
    "已删除 {username}": "Removed {username}",
    "后台运行中会自动刷新；如需手动同步请先停止后台": (
        "Background mode refreshes automatically. Stop it before syncing manually."
    ),
    "正在拉取课程、已选和统计…": "Loading courses, selections, and statistics…",
    "数据同步完成": "Data sync complete",
    "巡检间隔应在 10–3600 秒之间": "Poll interval must be between 10 and 3600 seconds.",
    "课程余量刷新应在 10–300 秒之间": (
        "Live course refresh must be between 10 and 300 seconds."
    ),
    "账号状态刷新应在 30–3600 秒之间": (
        "Account status refresh must be between 30 and 3600 seconds."
    ),
    "单账号最多已选应在 1–20 门之间": "Max selected per account must be between 1 and 20.",
    "设置格式有误": "Invalid settings",
    "保存失败": "Save failed",
    "设置已保存，后台下一轮生效": "Settings saved and will apply on the next cycle",
    "等待验证码超时": "Timed out waiting for the captcha.",
    "{username} 登录成功{suffix}": "{username} signed in successfully{suffix}",
    "登录失败": "Sign-in failed",
    "{username} 登录失败：\n{error}": "Could not sign in to {username}:\n{error}",
    "操作失败": "Operation failed",
    "{operation}失败：\n{error}": "{operation} failed:\n{error}",
    "执行任务": "Task run",
    "关闭控制台": "Close console",
    "后台任务仍在运行。关闭窗口不会停止自动选课与签到。\n\n确定关闭控制台吗？": (
        "The background runner is still active. Closing this window will not stop it.\n\n"
        "Close the console?"
    ),
    "语言已切换为 English": "Language switched to English",
    "语言已切换为中文": "语言已切换为中文",
}


def translate(text: str, language: str) -> str:
    if language == "en":
        return ENGLISH.get(text, text)
    return text


def format_text(text: str, language: str, **values: Any) -> str:
    return translate(text, language).format(**values)
