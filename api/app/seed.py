"""Reference data: the feeds we ingest and the vendors we tag.

Applied on startup with ON CONFLICT DO NOTHING, so editing a row here does not
overwrite it in the database. Add rows freely. Change existing ones with a migration.
"""

import logging

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Source, Stream, Vendor

log = logging.getLogger(__name__)

SOURCES: list[dict] = [
    # main: security news that becomes rows on the board
    {"name": "BleepingComputer", "feed_url": "https://www.bleepingcomputer.com/feed/", "site_url": "https://www.bleepingcomputer.com", "stream": Stream.main},
    {"name": "The Record", "feed_url": "https://therecord.media/feed", "site_url": "https://therecord.media", "stream": Stream.main},
    {"name": "SecurityWeek", "feed_url": "https://www.securityweek.com/feed/", "site_url": "https://www.securityweek.com", "stream": Stream.main},
    {"name": "Dark Reading", "feed_url": "https://www.darkreading.com/rss.xml", "site_url": "https://www.darkreading.com", "stream": Stream.main},
    {"name": "Krebs on Security", "feed_url": "https://krebsonsecurity.com/feed/", "site_url": "https://krebsonsecurity.com", "stream": Stream.main},
    # elsewhere: policy, privacy, culture. Shown in the right rail only.
    {"name": "EFF", "feed_url": "https://www.eff.org/rss/updates.xml", "site_url": "https://www.eff.org", "stream": Stream.elsewhere},
    {"name": "404 Media", "feed_url": "https://www.404media.co/rss/", "site_url": "https://www.404media.co", "stream": Stream.elsewhere},
    {"name": "Citizen Lab", "feed_url": "https://citizenlab.ca/feed/", "site_url": "https://citizenlab.ca", "stream": Stream.elsewhere},
    {"name": "Lawfare", "feed_url": "https://www.lawfaremedia.org/feeds/articles", "site_url": "https://www.lawfaremedia.org", "stream": Stream.elsewhere},
    {"name": "Wired", "feed_url": "https://www.wired.com/feed/category/security/latest/rss", "site_url": "https://www.wired.com/category/security/", "stream": Stream.elsewhere},
    {"name": "TechCrunch", "feed_url": "https://techcrunch.com/category/security/feed/", "site_url": "https://techcrunch.com/category/security/", "stream": Stream.elsewhere},
    {"name": "Ars Technica", "feed_url": "https://arstechnica.com/security/feed/", "site_url": "https://arstechnica.com/security/", "stream": Stream.elsewhere},
]

# Aliases are matched case-insensitively on word boundaries against title + first
# paragraph. Keep them specific: "Zoom" alone would tag every article that says "zoom in".
VENDORS: list[dict] = [
    {"slug": "microsoft", "name": "Microsoft", "domain": "microsoft.com", "aliases": ["Microsoft", "MSRC", "Windows", "Exchange Server", "SharePoint", "Azure", "Outlook", "Microsoft 365", "Hyper-V", "Patch Tuesday"]},
    {"slug": "fortinet", "name": "Fortinet", "domain": "fortinet.com", "aliases": ["Fortinet", "FortiOS", "FortiGate", "FortiManager", "FortiWeb", "FortiClient", "FortiProxy", "FortiSIEM"]},
    {"slug": "cisco", "name": "Cisco", "domain": "cisco.com", "aliases": ["Cisco", "IOS XE", "IOS XR", "NX-OS", "Cisco ASA", "Firepower", "Webex", "Talos"]},
    {"slug": "ivanti", "name": "Ivanti", "domain": "ivanti.com", "aliases": ["Ivanti", "Connect Secure", "Pulse Secure", "Policy Secure", "Ivanti EPMM", "MobileIron"]},
    {"slug": "vmware", "name": "VMware", "domain": "vmware.com", "aliases": ["VMware", "vCenter", "ESXi", "vSphere", "Workstation Pro", "Aria Operations"]},
    {"slug": "broadcom", "name": "Broadcom", "domain": "broadcom.com", "aliases": ["Broadcom", "Symantec"]},
    {"slug": "palo-alto-networks", "name": "Palo Alto Networks", "domain": "paloaltonetworks.com", "aliases": ["Palo Alto Networks", "PAN-OS", "GlobalProtect", "Cortex XDR", "Prisma Access", "Unit 42"]},
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
]


async def seed(session: AsyncSession) -> None:
    await session.execute(
        insert(Vendor)
        .values([{**v, "logo_path": f"/vendors/{v['slug']}.svg"} for v in VENDORS])
        .on_conflict_do_nothing(index_elements=["slug"])
    )
    await session.execute(
        insert(Source).values(SOURCES).on_conflict_do_nothing(index_elements=["feed_url"])
    )
    await session.commit()
    log.info("seed: %d sources, %d vendors ensured", len(SOURCES), len(VENDORS))
