"""Reference data: the feeds we ingest and the vendors we tag.

Applied on startup with ON CONFLICT DO NOTHING, so editing a row here does not
overwrite it in the database. Add rows freely. Change existing ones with a migration.
"""

import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Health, Source, Stream, Vendor

log = logging.getLogger(__name__)

SOURCES: list[dict] = [
    # main: security news that becomes rows on the board.
    # vendor_slug marks a vendor's own feed, which wins primary-source selection.
    {"name": "BleepingComputer", "feed_url": "https://www.bleepingcomputer.com/feed/", "site_url": "https://www.bleepingcomputer.com", "stream": Stream.main},
    {"name": "The Record", "feed_url": "https://therecord.media/feed", "site_url": "https://therecord.media", "stream": Stream.main},
    {"name": "SecurityWeek", "feed_url": "https://www.securityweek.com/feed/", "site_url": "https://www.securityweek.com", "stream": Stream.main},
    {"name": "Dark Reading", "feed_url": "https://www.darkreading.com/rss.xml", "site_url": "https://www.darkreading.com", "stream": Stream.main},
    {"name": "Krebs on Security", "feed_url": "https://krebsonsecurity.com/feed/", "site_url": "https://krebsonsecurity.com", "stream": Stream.main},
    {"name": "CISA", "feed_url": "https://www.cisa.gov/cybersecurity-advisories/all.xml", "site_url": "https://www.cisa.gov/news-events/cybersecurity-advisories", "stream": Stream.main,
     # 403 to httpx but 200 to curl: looks like TLS fingerprinting. curl_cffi is the likely fix.
     "enabled": False, "health": Health.disabled},
    {"name": "The Hacker News", "feed_url": "https://feeds.feedburner.com/TheHackersNews", "site_url": "https://thehackernews.com", "stream": Stream.main},
    {"name": "Rapid7", "feed_url": "https://www.rapid7.com/blog/rss/", "site_url": "https://www.rapid7.com/blog/", "stream": Stream.main},
    {"name": "Unit 42", "feed_url": "https://unit42.paloaltonetworks.com/feed/", "site_url": "https://unit42.paloaltonetworks.com", "stream": Stream.main},
    {"name": "Palo Alto Networks", "feed_url": "https://security.paloaltonetworks.com/rss.xml", "site_url": "https://security.paloaltonetworks.com", "stream": Stream.main, "vendor_slug": "palo-alto-networks"},
    # enrichment: fetched for data keyed by CVE, never rows. Handler in app/ingest.py.
    {"name": "MSRC", "feed_url": "https://api.msrc.microsoft.com/update-guide/rss", "site_url": "https://msrc.microsoft.com/update-guide", "stream": Stream.enrichment, "vendor_slug": "microsoft"},
    # elsewhere: policy, privacy, culture. Shown in the right rail only.
    {"name": "EFF", "feed_url": "https://www.eff.org/rss/updates.xml", "site_url": "https://www.eff.org", "stream": Stream.elsewhere},
    {"name": "404 Media", "feed_url": "https://www.404media.co/rss/", "site_url": "https://www.404media.co", "stream": Stream.elsewhere},
    {"name": "Citizen Lab", "feed_url": "https://citizenlab.ca/feed/", "site_url": "https://citizenlab.ca", "stream": Stream.elsewhere},
    {"name": "Lawfare", "feed_url": "https://www.lawfaremedia.org/feeds/articles", "site_url": "https://www.lawfaremedia.org", "stream": Stream.elsewhere},
    {"name": "Wired", "feed_url": "https://www.wired.com/feed/category/security/latest/rss", "site_url": "https://www.wired.com/category/security/", "stream": Stream.elsewhere},
    {"name": "TechCrunch", "feed_url": "https://techcrunch.com/category/security/feed/", "site_url": "https://techcrunch.com/category/security/", "stream": Stream.elsewhere},
    {"name": "Ars Technica", "feed_url": "https://arstechnica.com/security/feed/", "site_url": "https://arstechnica.com/security/", "stream": Stream.elsewhere},
]

# Aliases are matched case-insensitively on word boundaries (see app/tagging.py). The
# vendor name is not an alias unless listed. Keep them specific: bare "Intel" would tag
# "threat intel", bare "Arm" would tag "arm yourself".
VENDORS: list[dict] = [
    {"slug": "microsoft", "name": "Microsoft", "domain": "microsoft.com", "aliases": ["Microsoft", "MSRC", "Windows", "Exchange Server", "SharePoint", "Azure", "Outlook", "Microsoft 365", "Hyper-V", "Patch Tuesday"]},
    {"slug": "fortinet", "name": "Fortinet", "domain": "fortinet.com", "aliases": ["Fortinet", "FortiOS", "FortiGate", "FortiManager", "FortiWeb", "FortiClient", "FortiProxy", "FortiSIEM"]},
    {"slug": "cisco", "name": "Cisco", "domain": "cisco.com", "aliases": ["Cisco", "IOS XE", "IOS XR", "NX-OS", "Cisco ASA", "Firepower", "Webex", "Talos"]},
    {"slug": "ivanti", "name": "Ivanti", "domain": "ivanti.com", "aliases": ["Ivanti", "Connect Secure", "Pulse Secure", "Policy Secure", "Ivanti EPMM", "MobileIron"]},
    {"slug": "vmware", "name": "VMware", "domain": "vmware.com", "aliases": ["VMware", "vCenter", "ESXi", "vSphere", "Workstation Pro", "Aria Operations"]},
    {"slug": "broadcom", "name": "Broadcom", "domain": "broadcom.com", "aliases": ["Broadcom", "Symantec"]},
    {"slug": "palo-alto-networks", "name": "Palo Alto Networks", "domain": "paloaltonetworks.com", "aliases": ["Palo Alto Networks", "PAN-OS", "GlobalProtect", "Cortex XDR", "Prisma Access"]},
    {"slug": "atlassian", "name": "Atlassian", "domain": "atlassian.com", "aliases": ["Atlassian", "Confluence", "Jira", "Bitbucket", "Bamboo"]},
    {"slug": "gitlab", "name": "GitLab", "domain": "gitlab.com", "aliases": ["GitLab"]},
    {"slug": "github", "name": "GitHub", "domain": "github.com", "aliases": ["GitHub", "GitHub Actions", "GitHub Enterprise Server"]},
    {"slug": "okta", "name": "Okta", "domain": "okta.com", "aliases": ["Okta", "Auth0"]},
    {"slug": "apple", "name": "Apple", "domain": "apple.com", "aliases": ["Apple", "iOS", "iPadOS", "macOS", "Safari", "WebKit", "visionOS", "watchOS"]},
    {"slug": "google", "name": "Google", "domain": "google.com", "aliases": ["Google", "Chrome", "Chromium", "Android", "Pixel", "Google Cloud", "V8"]},
    {"slug": "mozilla", "name": "Mozilla", "domain": "mozilla.org", "aliases": ["Mozilla", "Firefox", "Thunderbird"]},
    {"slug": "oracle", "name": "Oracle", "domain": "oracle.com", "aliases": ["Oracle", "WebLogic", "E-Business Suite", "MySQL", "Java SE"]},
    {"slug": "sap", "name": "SAP", "domain": "sap.com", "aliases": ["SAP", "NetWeaver", "SAP S/4HANA"]},
    {"slug": "adobe", "name": "Adobe", "domain": "adobe.com", "aliases": ["Adobe", "Acrobat", "ColdFusion", "Magento", "Adobe Commerce", "Experience Manager"]},
    {"slug": "citrix", "name": "Citrix", "domain": "citrix.com", "aliases": ["Citrix", "NetScaler", "Citrix Bleed", "XenServer"]},
    {"slug": "f5", "name": "F5", "domain": "f5.com", "aliases": ["F5", "BIG-IP", "NGINX"]},
    {"slug": "juniper", "name": "Juniper Networks", "domain": "juniper.net", "aliases": ["Juniper", "Junos", "Junos OS"]},
    {"slug": "sonicwall", "name": "SonicWall", "domain": "sonicwall.com", "aliases": ["SonicWall", "SonicOS", "SMA 100"]},
    {"slug": "sophos", "name": "Sophos", "domain": "sophos.com", "aliases": ["Sophos"]},
    {"slug": "check-point", "name": "Check Point", "domain": "checkpoint.com", "aliases": ["Check Point", "Quantum Security Gateway"]},
    {"slug": "zyxel", "name": "Zyxel", "domain": "zyxel.com", "aliases": ["Zyxel"]},
    {"slug": "qnap", "name": "QNAP", "domain": "qnap.com", "aliases": ["QNAP", "QTS", "QuTS hero"]},
    {"slug": "synology", "name": "Synology", "domain": "synology.com", "aliases": ["Synology", "DiskStation"]},
    {"slug": "linux", "name": "Linux", "domain": "kernel.org", "aliases": ["Linux kernel", "glibc", "sudo", "OpenSSH", "systemd"]},
    {"slug": "red-hat", "name": "Red Hat", "domain": "redhat.com", "aliases": ["Red Hat", "RHEL", "OpenShift"]},
    {"slug": "apache", "name": "Apache", "domain": "apache.org", "aliases": ["Apache", "Tomcat", "Struts", "Log4j", "ActiveMQ", "OFBiz"]},
    {"slug": "wordpress", "name": "WordPress", "domain": "wordpress.org", "aliases": ["WordPress", "WooCommerce"]},
    {"slug": "jetbrains", "name": "JetBrains", "domain": "jetbrains.com", "aliases": ["JetBrains", "TeamCity", "YouTrack"]},
    {"slug": "progress", "name": "Progress Software", "domain": "progress.com", "aliases": ["Progress Software", "MOVEit", "WS_FTP", "Telerik", "WhatsUp Gold"]},
    {"slug": "solarwinds", "name": "SolarWinds", "domain": "solarwinds.com", "aliases": ["SolarWinds", "Serv-U", "Web Help Desk"]},
    {"slug": "veeam", "name": "Veeam", "domain": "veeam.com", "aliases": ["Veeam"]},
    {"slug": "crowdstrike", "name": "CrowdStrike", "domain": "crowdstrike.com", "aliases": ["CrowdStrike", "Falcon sensor"]},
    {"slug": "cloudflare", "name": "Cloudflare", "domain": "cloudflare.com", "aliases": ["Cloudflare"]},
    {"slug": "aws", "name": "Amazon Web Services", "domain": "aws.amazon.com", "aliases": ["AWS", "Amazon Web Services", "Amazon S3", "AWS Lambda"]},
    {"slug": "openssl", "name": "OpenSSL", "domain": "openssl.org", "aliases": ["OpenSSL"]},
    {"slug": "ibm", "name": "IBM", "domain": "ibm.com", "aliases": ["IBM", "QRadar", "WebSphere", "Aspera"]},
    {"slug": "nvidia", "name": "NVIDIA", "domain": "nvidia.com", "aliases": ["NVIDIA", "CUDA", "GeForce"]},
    {"slug": "amd", "name": "AMD", "domain": "amd.com", "aliases": ["AMD", "Ryzen", "EPYC", "Radeon"]},
    {"slug": "intel", "name": "Intel", "domain": "intel.com", "aliases": ["Intel Corporation", "Intel CPU", "Intel CPUs", "Intel processors", "Intel chips", "Intel SGX", "Intel TDX", "Intel ME", "Xeon"]},
    {"slug": "qualcomm", "name": "Qualcomm", "domain": "qualcomm.com", "aliases": ["Qualcomm", "Snapdragon"]},
    {"slug": "arm", "name": "Arm", "domain": "arm.com", "aliases": ["Arm Holdings", "Arm Mali", "Mali GPU", "Arm Cortex", "TrustZone"]},
    {"slug": "samsung", "name": "Samsung", "domain": "samsung.com", "aliases": ["Samsung", "Exynos"]},
    {"slug": "tp-link", "name": "TP-Link", "domain": "tp-link.com", "aliases": ["TP-Link", "Omada"]},
    {"slug": "d-link", "name": "D-Link", "domain": "dlink.com", "aliases": ["D-Link"]},
    {"slug": "ubiquiti", "name": "Ubiquiti", "domain": "ui.com", "aliases": ["Ubiquiti", "UniFi", "EdgeRouter"]},
    {"slug": "trend-micro", "name": "Trend Micro", "domain": "trendmicro.com", "aliases": ["Trend Micro", "Apex One", "Deep Security"]},
    {"slug": "connectwise", "name": "ConnectWise", "domain": "connectwise.com", "aliases": ["ConnectWise", "ScreenConnect"]},
    {"slug": "kaseya", "name": "Kaseya", "domain": "kaseya.com", "aliases": ["Kaseya", "Kaseya VSA"]},
    {"slug": "jenkins", "name": "Jenkins", "domain": "jenkins.io", "aliases": ["Jenkins"]},
    {"slug": "kubernetes", "name": "Kubernetes", "domain": "kubernetes.io", "aliases": ["Kubernetes", "K8s", "kubectl", "Ingress-NGINX", "Ingress NGINX"]},
    {"slug": "docker", "name": "Docker", "domain": "docker.com", "aliases": ["Docker", "Docker Desktop", "Docker Hub"]},
    {"slug": "npm", "name": "npm", "domain": "npmjs.com", "aliases": ["npm"]},
    {"slug": "pypi", "name": "PyPI", "domain": "pypi.org", "aliases": ["PyPI", "Python Package Index"]},
]


async def seed(session: AsyncSession) -> None:
    await session.execute(
        insert(Vendor)
        .values([{**v, "logo_path": f"/vendors/{v['slug']}.svg"} for v in VENDORS])
        .on_conflict_do_nothing(index_elements=["slug"])
    )
    vendor_ids = dict((await session.execute(select(Vendor.slug, Vendor.id))).all())
    # Every row needs the same keys for a multi-row insert.
    defaults = {"enabled": True, "health": Health.unknown}
    sources = [
        {**defaults, **{k: v for k, v in s.items() if k != "vendor_slug"},
         "vendor_id": vendor_ids.get(s.get("vendor_slug"))}
        for s in SOURCES
    ]
    await session.execute(
        insert(Source).values(sources).on_conflict_do_nothing(index_elements=["feed_url"])
    )
    await session.commit()
    log.info("seed: %d sources, %d vendors ensured", len(SOURCES), len(VENDORS))
