"""Display names for NVD CPE product slugs ("sharepoint_server" -> "SharePoint Server").

Order: the CNA's own product name when it names the same product, else word-by-word:
brand overrides, then acronyms, then title case. No lowercase product names on the board.
"""

# Words whose casing title-case gets wrong. Keys are lowercase CPE words.
WORDS = {
    # Microsoft
    "sharepoint": "SharePoint", "powershell": "PowerShell", "onedrive": "OneDrive", "onenote": "OneNote",
    "hyper-v": "Hyper-V", ".net": ".NET", "asp.net": "ASP.NET",
    # Apple / Google / browsers
    "ios": "iOS", "ipados": "iPadOS", "macos": "macOS", "tvos": "tvOS", "watchos": "watchOS",
    "visionos": "visionOS", "webkit": "WebKit", "chromeos": "ChromeOS",
    # Network and security vendors
    "pan-os": "PAN-OS", "globalprotect": "GlobalProtect", "fortios": "FortiOS", "fortigate": "FortiGate",
    "fortiproxy": "FortiProxy", "fortimanager": "FortiManager", "fortiweb": "FortiWeb",
    "forticlient": "FortiClient", "fortisiem": "FortiSIEM", "fortianalyzer": "FortiAnalyzer",
    "big-ip": "BIG-IP", "nginx": "NGINX", "routeros": "RouterOS", "asyncos": "AsyncOS", "nx-os": "NX-OS", "junos": "Junos", "sonicos": "SonicOS", "netscaler": "NetScaler",
    "velocloud": "VeloCloud", "vcenter": "vCenter", "vsphere": "vSphere", "esxi": "ESXi", "nsx": "NSX",
    "unifi": "UniFi", "edgerouter": "EdgeRouter", "screenconnect": "ScreenConnect", "moveit": "MOVEit",
    "whatsup": "WhatsUp", "teamcity": "TeamCity", "youtrack": "YouTrack",
    "qradar": "QRadar", "websphere": "WebSphere", "weblogic": "WebLogic", "peoplesoft": "PeopleSoft",
    "peopletools": "PeopleTools", "netweaver": "NetWeaver", "coldfusion": "ColdFusion",
    # Open source
    "gitlab": "GitLab", "github": "GitHub", "wordpress": "WordPress", "woocommerce": "WooCommerce",
    "phpmyadmin": "phpMyAdmin", "openssl": "OpenSSL", "openssh": "OpenSSH", "mysql": "MySQL",
    "postgresql": "PostgreSQL", "mariadb": "MariaDB", "mongodb": "MongoDB", "node.js": "Node.js",
    "activemq": "ActiveMQ", "ofbiz": "OFBiz", "log4j": "Log4j", "openshift": "OpenShift",
    "kubernetes": "Kubernetes", "jenkins": "Jenkins", "roundcube": "Roundcube", "rabbitmq": "RabbitMQ",
    "graphql": "GraphQL", "javascript": "JavaScript", "typescript": "TypeScript", "php": "PHP",
    "v8": "V8", "ffmpeg": "FFmpeg", "imagemagick": "ImageMagick", "libreoffice": "LibreOffice",
    "thunderbird": "Thunderbird", "firefox": "Firefox", "zimbra": "Zimbra",
}

ACRONYMS = {
    "api", "vpn", "ssl", "tls", "ssh", "ftp", "sftp", "http", "https", "dns", "sql", "cms", "crm", "erp",
    "iot", "ai", "ui", "os", "ad", "ldap", "saml", "sso", "mfa", "rdp", "smb", "nas", "san", "vm", "xdr",
    "edr", "siem", "soar", "waf", "apm", "ltm", "asm", "asa", "ftd", "ise", "sma", "sra", "utm", "ips",
    "ids", "pdf", "xml", "json", "rest", "soap", "cli", "sdk", "jdk", "jre", "usb", "bios", "uefi", "tpm",
    "cpu", "gpu", "lte", "wlan", "wan", "lan", "vpc", "ec2", "s3", "iam", "kms", "aws", "gcp", "hpe",
    "ibm", "sap", "amd", "hp", "lg", "tp-link", "d-link", "jboss", "ucs", "dcnm", "wsa", "esa",
}


def _word(w: str) -> str:
    low = w.lower()
    if low in WORDS:
        return WORDS[low]
    if low in ACRONYMS:
        return low.upper()
    if "-" in w:  # multi-domain -> Multi-Domain, big-ip handled above
        return "-".join(_word(p) for p in w.split("-"))
    if any(ch.isdigit() for ch in w) and any(ch.isalpha() for ch in w):
        return w.upper() if len(w) <= 4 else w  # 22h2 -> 22H2, r81 -> R81; long mixed tokens left alone
    return w[:1].upper() + w[1:]


# Overrides that span two slug parts.
PHRASES = {"ios_xe": "IOS XE", "ios_xr": "IOS XR", "ws_ftp": "WS_FTP", "visual_studio": "Visual Studio"}


def display_name(cpe_slug: str) -> str:
    """"sharepoint_server" -> "SharePoint Server", "big-ip_access_policy_manager" -> "BIG-IP Access Policy Manager"."""
    parts = [p for p in cpe_slug.strip().lower().split("_")]
    out: list[str] = []
    i = 0
    while i < len(parts):
        pair = f"{parts[i]}_{parts[i + 1]}" if i + 1 < len(parts) else None
        if pair in PHRASES:
            out.append(PHRASES[pair])
            i += 2
            continue
        if parts[i]:
            out.append(_word(parts[i]))
        i += 1
    return " ".join(out)
