import json
import re

raw = json.load(open('errors_raw.json', encoding='utf-8'))
PARAM_PREFIXES = [(p['prefix'], p['suffix']) for p in raw['parameterized']]
PARAM_PATTERNS = {f"{p['prefix']}X{p['suffix']}" for p in raw['parameterized']}


def classify_http(code):
    if code.startswith('FLOOD_'):
        return 420
    if code in ('AUTH_KEY_INVALID', 'AUTH_KEY_DUPLICATED', 'AUTH_KEY_PERM_EMPTY', 'AUTH_KEY_UNREGISTERED',
                'SESSION_REVOKED', 'SESSION_EXPIRED', 'SESSION_PASSWORD_NEEDED', 'USER_DEACTIVATED',
                'USER_DEACTIVATED_BAN', 'AUTH_TOKEN_EXPIRED', 'AUTH_TOKEN_INVALID',
                'ACCESS_TOKEN_EXPIRED', 'ACCESS_TOKEN_INVALID') or code.startswith('AUTH_TOKEN_'):
        return 401
    if code.startswith('NETWORK_MIGRATE_') or code.startswith('PHONE_MIGRATE_') or \
       code.startswith('USER_MIGRATE_') or code.startswith('FILE_MIGRATE_') or \
       code.startswith('STATS_MIGRATE_'):
        return 303
    if code in ('USER_NOT_PARTICIPANT', 'CHAT_NOT_MODIFIED', 'CHANNEL_PRIVATE',
                'CHANNEL_PUBLIC_GROUP_NA', 'CHANNELS_TOO_MUCH') or \
       code.endswith('_FORBIDDEN') or code.startswith('RIGHT_') or \
       'PRIVACY' in code or 'RESTRICTED' in code or code.endswith('_BANNED'):
        return 403
    if code.endswith('_NOT_FOUND') or code in ('USER_NOT_FOUND', 'CHAT_NOT_FOUND', 'PEER_ID_INVALID',
                                                'MSG_ID_INVALID', 'CONNECTION_NOT_INITED',
                                                'INPUT_USER_DEACTIVATED'):
        return 404 if code.endswith('_NOT_FOUND') else 400
    if 'TIMEOUT' in code or code == 'TIMEOUT':
        return 500
    return 400


CATEGORY_MAP = [
    ('Flood / Rate limits', lambda c: c.startswith('FLOOD_') or 'SLOWMODE' in c or 'TOO_MUCH' in c),
    ('Authentication', lambda c: c.startswith('AUTH_') or c.startswith('ACCESS_TOKEN') or
        c.startswith('SESSION_') or c.startswith('2FA_') or c.startswith('PASSWORD_') or
        c.startswith('SRP_') or c.startswith('EMAIL_') or c.startswith('CODE_') or
        c.startswith('PHONE_CODE_') or c.startswith('PHONE_NUMBER_') or c == 'TOKEN_INVALID'),
    ('Permissions / Forbidden', lambda c: c.endswith('_FORBIDDEN') or c.startswith('RIGHT_') or
        c.startswith('ADMIN_') or c.startswith('CHAT_ADMIN_') or 'PRIVACY' in c or
        'RESTRICTED' in c or c.endswith('_BANNED') or 'NOT_ALLOWED' in c),
    ('Migration', lambda c: c.startswith('NETWORK_MIGRATE_') or c.startswith('PHONE_MIGRATE_') or
        c.startswith('USER_MIGRATE_') or c.startswith('FILE_MIGRATE_') or c.startswith('STATS_MIGRATE_')),
    ('Channels & Chats', lambda c: c.startswith('CHANNEL_') or c.startswith('CHAT_') or
        c.startswith('MEGAGROUP_') or c.startswith('BROADCAST_')),
    ('Users & Peers', lambda c: c.startswith('USER_') or c.startswith('PEER_') or
        c.startswith('INPUT_USER_') or c.startswith('CONTACT_') or c.startswith('USERNAME_')),
    ('Bots & Inline', lambda c: c.startswith('BOT_') or c.startswith('INLINE_') or
        c.startswith('QUERY_ID_') or c.startswith('START_PARAM_')),
    ('Media / Files', lambda c: c.startswith('FILE_') or c.startswith('PHOTO_') or
        c.startswith('VIDEO_') or c.startswith('DOCUMENT_') or c.startswith('AUDIO_') or
        c.startswith('IMAGE_') or c.startswith('MEDIA_') or c.startswith('STICKER_') or
        c.startswith('STICKERSET_') or c.startswith('GIF_') or c.startswith('WALLPAPER_')),
    ('Messages', lambda c: c.startswith('MESSAGE_') or c.startswith('MSG_') or
        c.startswith('REPLY_') or c.startswith('REACTION_') or c.startswith('SCHEDULE_') or
        c.startswith('SEND_AS_') or c.startswith('FORWARD_')),
    ('Payments / Stars', lambda c: c.startswith('PAYMENT_') or c.startswith('PREMIUM_') or
        c.startswith('STARS_') or c.startswith('STAR_') or c.startswith('INVOICE_') or
        c.startswith('SUBSCRIPTION_')),
    ('Stories', lambda c: c.startswith('STORY_') or c.startswith('STORIES_')),
    ('Calls / Voice / Video', lambda c: c.startswith('CALL_') or c.startswith('GROUPCALL_') or
        c.startswith('GROUP_CALL_') or c.startswith('VOICE_') or c.startswith('CONFERENCE_')),
    ('Polls & Quizzes', lambda c: c.startswith('POLL_') or c.startswith('QUIZ_')),
    ('Folders / Filters', lambda c: c.startswith('FOLDER_') or c.startswith('FILTER_') or
        c.startswith('DIALOG_FILTERS_')),
    ('Boost / Levels', lambda c: c.startswith('BOOST_') or c.startswith('LEVEL_')),
    ('Server / Internal', lambda c: c == 'TIMEOUT' or c.startswith('CONNECTION_') or
        'INTERDC_' in c or c.startswith('API_') or c == 'WORKER_BUSY_TOO_LONG_RETRY'),
    ('Topics', lambda c: c.startswith('TOPIC_')),
    ('Invites', lambda c: c.startswith('INVITE_')),
    ('Themes & Wallpapers', lambda c: c.startswith('THEME_') or c.startswith('WALLPAPER_')),
    ('Web previews', lambda c: c.startswith('WEBPAGE_') or c.startswith('WEBDOCUMENT_') or c.startswith('URL_')),
]


def categorize(code):
    for name, pred in CATEGORY_MAP:
        if pred(code):
            return name
    return 'Other'


def words_of(code):
    return code.lower().split('_')


def human_phrase_from_subject(words):
    return ' '.join(w for w in words if w not in ('the', 'a', 'an'))


WHY_TEMPLATES = [
    (lambda c: c == 'FLOOD_WAIT_X',
        'Too many requests in too short a window. Wait the supplied number of seconds before retrying; the gogram client schedules this automatically.'),
    (lambda c: c == 'FLOOD_PREMIUM_WAIT_X',
        'A flood limit specific to premium-only methods was hit. Sleep for the supplied seconds before retrying.'),
    (lambda c: c == 'SLOWMODE_WAIT_X',
        'Slow-mode is enabled in this chat; the bot/user must wait the given number of seconds before sending another message there.'),
    (lambda c: c == 'STORY_SEND_FLOOD_WEEKLY_X',
        "The account hit its weekly story-posting cap. Wait the supplied seconds — usually a fresh quota arrives at the start of the next week."),
    (lambda c: c == 'STORY_SEND_FLOOD_MONTHLY_X',
        "The account hit its monthly story-posting cap. Wait the supplied seconds before posting again."),
    (lambda c: c == 'TAKEOUT_INIT_DELAY_X',
        'For security, account-data export is delayed; the supplied seconds must elapse before account.initTakeoutSession will succeed.'),
    (lambda c: c == 'SESSION_TOO_FRESH_X',
        'The current session was created less than 24h ago and is not allowed to perform this sensitive action yet. Wait the supplied seconds.'),
    (lambda c: c == 'PASSWORD_TOO_FRESH_X',
        'The 2FA password was changed recently and is still under cooldown for sensitive operations. Wait the supplied seconds.'),
    (lambda c: c == 'PREVIOUS_CHAT_IMPORT_ACTIVE_WAIT_XMIN',
        'A previous chat-history import is still running; wait the supplied minutes before starting a new one.'),
    (lambda c: c == 'PREMIUM_SUB_ACTIVE_UNTIL_X',
        'The current account already has an active premium subscription until the supplied unix timestamp — no new purchase is needed.'),
    (lambda c: c == 'NETWORK_MIGRATE_X',
        'The auth key/account lives on a different data center. Reconnect to DC X and replay the request; the gogram client handles this transparently.'),
    (lambda c: c == 'PHONE_MIGRATE_X',
        'The phone number is registered on a different DC. Re-issue the auth call against DC X.'),
    (lambda c: c == 'USER_MIGRATE_X',
        'The current user lives on a different DC. Reconnect to DC X before retrying.'),
    (lambda c: c == 'FILE_MIGRATE_X',
        'The requested file lives on a different DC. Re-issue the upload/download against DC X.'),
    (lambda c: c == 'STATS_MIGRATE_X',
        'Channel statistics for this channel are stored on a different DC. Re-issue the stats call against DC X.'),
    (lambda c: c == 'AUTH_KEY_INVALID',
        'The auth key the client is using has been revoked or never existed. The session must be re-created from scratch (re-login).'),
    (lambda c: c == 'AUTH_KEY_UNREGISTERED',
        'The auth key was deleted on the server. The session is dead; sign in again.'),
    (lambda c: c == 'AUTH_KEY_DUPLICATED',
        'Two clients used the same auth key concurrently. Both sessions are terminated; sign in again from this client.'),
    (lambda c: c == 'SESSION_REVOKED',
        'The user revoked this session from another device. Drop the session and re-authenticate.'),
    (lambda c: c == 'SESSION_EXPIRED',
        'The session has been idle long enough that the server discarded it. Re-authenticate to start a new one.'),
    (lambda c: c == 'SESSION_PASSWORD_NEEDED',
        '2FA is enabled on this account. After SignIn returns this, call account.getPassword and complete checkPassword.'),
    (lambda c: c == 'USER_DEACTIVATED',
        'The account has been deactivated (deleted by the user or by Telegram). No further requests will succeed on this auth key.'),
    (lambda c: c == 'USER_DEACTIVATED_BAN',
        'The account was banned by Telegram for ToS violations. The account is permanently unusable.'),
    (lambda c: c == 'PHONE_NUMBER_BANNED',
        'The supplied phone number is banned from Telegram and cannot be used to register or sign in.'),
    (lambda c: c == 'PHONE_NUMBER_INVALID',
        'The phone number does not match the expected E.164 format or is otherwise unrecognized.'),
    (lambda c: c == 'PHONE_CODE_INVALID',
        'The login code the user entered is wrong. Prompt them again; after several failures the code is invalidated.'),
    (lambda c: c == 'PHONE_CODE_EXPIRED',
        'The login code timed out before SignIn was called. Request a new code via auth.resendCode.'),
    (lambda c: c == 'PASSWORD_HASH_INVALID',
        'The 2FA password check failed. Either the password is wrong or the SRP parameters were stale — re-fetch account.getPassword and retry.'),
    (lambda c: c == 'CHAT_ADMIN_REQUIRED',
        'The action requires chat-admin rights and the calling user does not have them.'),
    (lambda c: c == 'CHANNEL_PRIVATE',
        'The channel is private and the current user is not a member, or it has been banned/kicked.'),
    (lambda c: c == 'CHANNEL_INVALID',
        'The channel id does not point to a real channel — usually a stale or malformed InputChannel.'),
    (lambda c: c == 'CHAT_WRITE_FORBIDDEN',
        "The user is muted or banned from posting in this chat (e.g. send_messages right disabled or restricted by an admin)."),
    (lambda c: c == 'PEER_ID_INVALID',
        "The supplied peer (user/chat/channel id) is unknown to the server — usually a stale or wrongly-resolved InputPeer."),
    (lambda c: c == 'USER_NOT_PARTICIPANT',
        'The target user is not a participant of this chat/channel, so the requested per-member action cannot be performed.'),
    (lambda c: c == 'USER_PRIVACY_RESTRICTED',
        "Privacy settings prevent this action (e.g. the target user disallows being added to groups, called, or messaged by strangers)."),
    (lambda c: c == 'BOT_INVALID',
        'The InputUser does not resolve to a bot — passed a regular user where a bot was required.'),
    (lambda c: c == 'BOT_METHOD_INVALID',
        'The current user is a bot, but the called method is not available to bots (or vice-versa).'),
    (lambda c: c == 'INPUT_USER_DEACTIVATED',
        "The user referenced by the InputUser has deleted their account."),
    (lambda c: c == 'MESSAGE_NOT_MODIFIED',
        'editMessage was called with the exact same text/markup the message already has — server refuses to no-op edit.'),
    (lambda c: c == 'MESSAGE_ID_INVALID' or c == 'MSG_ID_INVALID',
        'The message id does not exist in this peer (already deleted, never existed, or wrong chat).'),
    (lambda c: c == 'MESSAGE_TOO_LONG',
        'The message text exceeds the per-message byte limit. Split it into multiple messages.'),
    (lambda c: c == 'CHAT_NOT_MODIFIED',
        'The requested chat update would not change anything (e.g. setting the same title or photo) — server refuses.'),
    (lambda c: c == 'FILE_REFERENCE_EXPIRED',
        'A previously-issued file reference has aged out. Re-fetch the message/photo/document to get a fresh reference, then retry.'),
    (lambda c: c == 'FILE_PARTS_INVALID' or c == 'FILE_PART_INVALID',
        'Upload state is inconsistent — wrong part count, wrong size, or parts uploaded out of band. Restart the upload.'),
    (lambda c: c == 'TIMEOUT',
        "The server did not respond within the protocol's timeout window. Retry; if persistent, suspect network or DC issues."),
    (lambda c: c == 'CHANNELS_TOO_MUCH',
        "The user is already a member of the maximum number of channels/supergroups. They must leave some before joining/creating more."),
    (lambda c: c == 'ADMINS_TOO_MUCH',
        'The chat already has the maximum number of admins permitted by Telegram. Demote someone before promoting a new admin.'),
]


def template_why(code):
    for pred, text in WHY_TEMPLATES:
        if pred(code):
            return text
    return None


def humanize_subject(parts):
    if not parts:
        return 'value'
    txt = ' '.join(parts)
    txt = txt.replace(' id ', ' ID ').replace(' id$', ' ID')
    return txt


def rule_why(code, message):
    words = code.split('_')
    last = words[-1] if words else ''
    head = words[0] if words else ''
    subject_words = [w.lower() for w in words[:-1]] if len(words) > 1 else [w.lower() for w in words]

    if last == 'INVALID':
        subj = humanize_subject(subject_words) or 'value'
        return f"The supplied {subj} is malformed, points to nothing the server recognises, or fails a server-side validity check."
    if last in ('EMPTY', 'MISSING'):
        subj = humanize_subject(subject_words) or 'value'
        return f"A required {subj} was omitted from the request. Populate it and retry."
    if last in ('EXPIRED',):
        subj = humanize_subject(subject_words) or 'value'
        return f"The {subj} has aged out. Request a fresh one and retry."
    if last == 'BANNED':
        subj = humanize_subject(subject_words)
        return f"The {subj} is blocked by Telegram for ToS reasons; the action cannot proceed."
    if last == 'FORBIDDEN':
        subj = humanize_subject(subject_words)
        return f"The current user is not allowed to perform this action on the targeted {subj} (permission or privacy restriction)."
    if 'TOO_LONG' in code:
        subj = humanize_subject([w.lower() for w in words[:words.index('TOO')]])
        return f"The {subj} exceeds the maximum length the server accepts. Shorten it."
    if 'TOO_MUCH' in code or 'TOO_MANY' in code:
        subj = humanize_subject([w.lower() for w in words[:max(words.index('TOO'), 0)]])
        return f"The account already has the maximum number of {subj} allowed. Remove some before adding more."
    if 'TOO_SHORT' in code:
        subj = humanize_subject([w.lower() for w in words[:words.index('TOO')]])
        return f"The {subj} is shorter than the minimum the server accepts."
    if 'NOT_FOUND' in code:
        subj = humanize_subject([w.lower() for w in words[:words.index('NOT')]])
        return f"No {subj} matching the request exists on the server (already deleted, wrong id, or not yet propagated)."
    if 'NOT_MODIFIED' in code:
        subj = humanize_subject([w.lower() for w in words[:words.index('NOT')]])
        return f"The request would not change the current {subj} — server rejects no-op edits."
    if 'NOT_ALLOWED' in code:
        idx = words.index('NOT')
        subj = humanize_subject([w.lower() for w in words[:idx]])
        return f"This account/peer is not permitted to perform the requested {subj} action."
    if 'NOT_AVAILABLE' in code:
        idx = words.index('NOT')
        subj = humanize_subject([w.lower() for w in words[:idx]])
        return f"The {subj} feature is disabled for this account, peer, or region."
    if 'ALREADY' in code:
        idx = words.index('ALREADY')
        rest = ' '.join(w.lower() for w in words[idx+1:])
        subj = ' '.join(w.lower() for w in words[:idx]) or 'target'
        return f"The {subj} is already {rest.replace('_', ' ')}; the operation would be a no-op."
    if 'WAIT' in code:
        return 'The server is rate-limiting this operation. Sleep for the duration the server reports before retrying.'
    if head == 'BOOST':
        return 'Boost-related precondition not met (insufficient boost level, slot already used, or wrong peer).'
    if head == 'STORY' or head == 'STORIES':
        return 'Story-specific precondition failed — usually the story is gone, the user lacks access, or a per-account story quota is hit.'
    if head == 'PAYMENT' or head == 'PREMIUM' or head == 'STARS' or head == 'STAR':
        return 'A payment, premium, or stars-purchase precondition failed. The user must complete the relevant purchase/auth flow first.'
    if head == 'POLL' or head == 'QUIZ':
        return 'Poll/quiz state precondition failed — usually the poll is closed, the choice is malformed, or the user already voted.'
    return f"{message.rstrip('.')}. Treated by gogram as a regular API error; inspect ErrResponseCode.Message for the exact code."


errors = []
for e in raw['errors']:
    code = e['code']
    msg = e['message']
    why = template_why(code) or rule_why(code, msg)
    errors.append({
        'code': code,
        'http': classify_http(code),
        'category': categorize(code),
        'message': msg,
        'why': why,
        'parameterized': code in PARAM_PATTERNS,
    })

errors.sort(key=lambda e: (e['http'], e['category'], e['code']))

with open('errors.json', 'w', encoding='utf-8') as f:
    json.dump({
        'errors': errors,
        'bad_msg_codes': raw['bad_msg_codes'],
        'parameterized': raw['parameterized'],
    }, f, indent=2, ensure_ascii=False)

categories = {}
http_codes = {}
for e in errors:
    categories[e['category']] = categories.get(e['category'], 0) + 1
    http_codes[e['http']] = http_codes.get(e['http'], 0) + 1

print(f'wrote errors.json with {len(errors)} entries')
print('by HTTP code:', sorted(http_codes.items()))
print('by category:', sorted(categories.items(), key=lambda x: -x[1]))
print('--- sample ---')
for e in errors[:3]:
    print(e)
print('---')
for e in errors[300:303]:
    print(e)
