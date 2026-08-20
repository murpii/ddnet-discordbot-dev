ban_appeal_m = {
    "en": {
        "title": "Ban Appeal Ticket",
        "ip_label": "Your IP address from https://ipinfo.io/ip",
        "privacy_note": (
            "Your IP address is provided voluntarily. It is used only to check whether you have a "
            "matching ban or flagged IP on our servers, is never shared or sold, and is not stored "
            "in full (only a shortened form is kept in the appeal record). An appeal is declined if "
            "nothing matching is found."
        ),
        "ip_placeholder": "Example: 192.168.2.100",
        "name_label": "Your in-game name",
        "name_placeholder": "nameless tee",
        "reason_label": "The ban reason shown in the ban message",
        "reason_placeholder": "I.e blocking is prohibited",
        "appeal_label": "Your appeal message.",
        "appeal_placeholder": "Be clear and honest about what happened and "
                              "take responsibility for actions that led to your ban.",
    },
    "de": {
        "title": "Entbannungsanfrage",
        "ip_label": "Deine öffentliche IP von https://ipinfo.io/ip",
        "ip_placeholder": "Beispiel: 192.168.2.100",
        "name_label": "Dein Ingame-Name",
        "name_placeholder": "nameless tee",
        "reason_label": "Der Bann-Grund laut Bannnachricht",
        "reason_placeholder": "z.B. blocking is prohibited",
        "appeal_label": "Deine Nachricht",
        "appeal_placeholder": "Erkläre ehrlich was passiert ist und übernimm Verantwortung",
    },
    "ru": {
        "title": "Апелляция блокировки",
        "ip_label": "Ваш IP адресс с сайта https://ipinfo.io/ip",
        "ip_placeholder": "Например: 192.168.2.100",
        "name_label": "Ваш игровой никнейм",
        "name_placeholder": "nnameless tee",
        "reason_label": "Причина бана из сообщения о блокировке",
        "reason_placeholder": "Например: blocking is prohibited (блок запрещён)",
        "appeal_label": "Напишите Ваше обжалование",
        "appeal_placeholder": "Четко и честно опишите ситуацию и "
                              "примите ответственность за действия приведшие к Вашему бану",
    },
}

# Messages shown by the ban-appeal gate (before a ticket is opened).
# Only "en" is filled in for now; other languages fall back to English.
BAN_APPEAL_GATE = {
    "en": {
        "not_banned_title": "No active ban found",
        "not_banned": (
            "We couldn't find an active ban for the IP `{ip}`.\n\n"
            "- Double-check your public IP at https://ipinfo.io/ip -- it can change over time.\n"
            "- If you were banned, the ban may have already expired.\n\n"
            "If you still believe this is a mistake, create an Admin-Mail ticket."
        ),
        "dnsbl_white_title": "IP not flagged",
        "dnsbl_white": (
            "Our checks didn't flag the IP `{ip}` (no VPN, proxy or datacenter detected), "
            "so a ban appeal can't be opened for it here.\n\n"
            "If you were banned on a different connection, re-check your public IP at "
            "https://ipinfo.io/ip, or contact staff directly."
        ),
        "near_expiry_title": "Your ban is about to expire",
        "near_expiry": (
            "Heads up — the ban on `{ip}` is set to expire {expires}.\n"
            "**Reason:** {reason}\n\n"
            "It may be quicker to simply wait it out. Do you still want to open a ban appeal?"
        ),
        "near_expiry_continue": "Continue appeal",
        "near_expiry_cancel": "Never mind",
        "cancelled": "No problem — no ban appeal was opened. You can start one again any time.",
        "opening": "Opening your ban appeal…",
    },
}

BAN_APPEAL_CLOUDFLARE = {
    "en": {
        "description": "The IP address you provided belongs to Cloudflare. "
                       "To play on official DDNet servers, you'll need to disable or uninstall Cloudflare WARP "
                       "from your device, as IPs from this service are flagged as VPNs in our system.",
        "title": "How to uninstall Cloudflare WARP:",
        "value": "Documentation"
    },
    "de": {
        "description": "Die von dir angegebene IP-Adresse gehört zu Cloudflare. "
                       "Um auf offiziellen DDNet-Servern zu spielen, musst du Cloudflare WARP auf deinem Gerät "
                       "deaktivieren oder deinstallieren, da IPs dieses Dienstes in unserem System als VPNs erkannt werden.",
        "title": "Cloudflare WARP deinstallieren:",
        "value": "Dokumentation"
    },
    "ru": {
        "description": "IP-адрес, который вы предоставили, относится к Cloudflare. "
                       "Чтобы играть на оффициальных серверах DDNet Вам необходимо отключить или удалить Cloudflare WARP "
                       "с вашего устройства, т.к. их предоставляемые IP-адреса помечаются как VPN-ы в нашей системе.",
        "title": "Как удалить Cloudflare WARP:",
        "value": "Документация"
    }
}
