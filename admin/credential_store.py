# -*- coding: utf-8 -*-
"""
Name: credential_store.py
Developed by: Julie Tripp (assisted)
Date: 2026-06-08

================================================================================
WHAT THIS MODULE PROVIDES  (cross-cutting helper for the AGOL -> RRGOrg migration)
================================================================================
Read/write the migration workflow's logins from the WINDOWS CREDENTIAL MANAGER so the scripts can
run unattended, and fall back to an interactive prompt (as today) when a credential is not stored.

Three logical credentials (Generic credentials in Credential Manager):
  * agol    -> nbs_agol_user      -- your AGOL account
  * portal  -> nbs_arcgis_admin   -- your ArcGIS Enterprise (Portal) admin account
  * GPUser  -> nbs_arcgis_gpuser  -- the low-priv portal account embedded as stored credentials

Backends, in order: pywin32 `win32cred` (preferred -- one entry holds username + password), then
`keyring` (WinVaultKeyring). If neither is importable, the store is a no-op and scripts simply prompt.

PUBLIC API
  resolve(key, label, default_username="", allow_save=True, log=print) -> (username, password)
      The function scripts call: returns a stored credential, else prompts (getpass) and optionally
      offers to save it. `key` is 'agol' | 'portal' | 'GPUser' (or a raw target name).
  connect(portal_url, key=None, default_username="", allow_pro_fallback=True, allow_prompt_fallback=True,
          sign_in_arcpy=False, log=print, **gis_kwargs) -> arcgis.gis.GIS
      Connect to an ArcGIS portal (Enterprise OR ArcGIS Online) reusing the stored login. CREDENTIALS
      FIRST (deliberately NOT GIS("pro") first); then (fallback) the active Pro session if it is signed in
      to the same portal; then (last resort) a username/password prompt that retries and offers to save the
      working login. `key` defaults to 'agol' for *.arcgis.com hosts, else 'portal'. Set allow_pro_fallback
      / allow_prompt_fallback False for an unattended run that must fail fast instead of blocking on input.
      sign_in_arcpy=True ALSO does arcpy.SignInToPortal (for scripts mixing arcpy + the arcgis API; most
      only need GIS() and leave it False) -- FATAL if that sign-in fails. Extra **gis_kwargs (e.g.
      verify_cert=False) pass through to GIS().
      The 'arcgis' package is imported lazily, so this module stays usable for pure credential operations.
  get_credential(target) / set_credential(target, user, pwd) / delete_credential(target) / list_targets()

================================================================================
CLI -- store credentials once, then runs are unattended
================================================================================
    python credential_store.py set agol         # prompts username + password (password hidden), stores
    python credential_store.py set portal
    python credential_store.py set GPUser
    python credential_store.py get agol          # shows username only; never prints the password
    python credential_store.py list
    python credential_store.py delete GPUser
"""

import sys
import getpass

# Credential Manager target (entry) names.
TARGETS = {
    "agol":   "nbs_agol_user",
    "portal": "nbs_arcgis_admin",
    "GPUser": "nbs_arcgis_gpuser",
}

# --- backend detection -------------------------------------------------------
_BACKEND = None
try:
    import win32cred
    import pywintypes
    _BACKEND = "win32cred"
except Exception:
    try:
        import keyring
        _BACKEND = "keyring"
    except Exception:
        _BACKEND = None

# keyring stores username + password as two entries under one target (it is password-only per key).
_KR_USER_KEY = "__username__"


def backend_name():
    return _BACKEND or "none"


def _target(key):
    return TARGETS.get(key, key)


def get_credential(target):
    """Return (username, password) for a target name, or (None, None) if not stored / no backend."""
    if _BACKEND == "win32cred":
        try:
            cred = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)
        except pywintypes.error:
            return None, None
        user = cred.get("UserName") or ""
        blob = cred.get("CredentialBlob")
        pwd = ""
        if blob:
            pwd = blob.decode("utf-16-le") if isinstance(blob, (bytes, bytearray)) else str(blob)
        return (user or None), (pwd or None)
    if _BACKEND == "keyring":
        user = keyring.get_password(target, _KR_USER_KEY)
        pwd = keyring.get_password(target, user) if user else None
        return (user or None), (pwd or None)
    return None, None


def set_credential(target, username, password):
    """Store username + password for a target name in the Windows Credential Manager. Returns True/False."""
    if _BACKEND == "win32cred":
        cred = {
            "Type": win32cred.CRED_TYPE_GENERIC,
            "TargetName": target,
            "UserName": username,
            "CredentialBlob": password,                 # pywin32 writes the wide string
            "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
        }
        win32cred.CredWrite(cred, 0)
        return True
    if _BACKEND == "keyring":
        keyring.set_password(target, _KR_USER_KEY, username)
        keyring.set_password(target, username, password)
        return True
    return False


def delete_credential(target):
    """Remove a stored credential. Returns True if removed, False if absent / no backend."""
    if _BACKEND == "win32cred":
        try:
            win32cred.CredDelete(target, win32cred.CRED_TYPE_GENERIC)
            return True
        except pywintypes.error:
            return False
    if _BACKEND == "keyring":
        user = keyring.get_password(target, _KR_USER_KEY)
        try:
            if user:
                keyring.delete_password(target, user)
            keyring.delete_password(target, _KR_USER_KEY)
            return True
        except Exception:
            return False
    return False


def list_targets():
    """List stored target names belonging to this workflow (the TARGETS entry names; 
    excludes any other Credential Manager entries). Returns a list of target names."""
    known = set(TARGETS.values())
    found = []
    if _BACKEND == "win32cred":
        try:
            for c in win32cred.CredEnumerate(None, 0):
                tn = c.get("TargetName", "")
                if tn in known:
                    found.append(tn)
        except pywintypes.error:
            pass
    elif _BACKEND == "keyring":
        # keyring has no portable enumerate; report the known targets that resolve.
        for t in TARGETS.values():
            if keyring.get_password(t, _KR_USER_KEY):
                found.append(t)
    return found


def resolve(key, label, default_username="", allow_save=True, log=print):
    """Return (username, password). Try the Credential Manager first; if not found, PROMPT (username
    with optional default + hidden password) exactly as the scripts do today, then optionally offer to
    save it for future unattended runs. `key` is 'agol'|'portal'|'GPUser' or a raw target name."""
    target = _target(key)
    user, pwd = get_credential(target)
    if user and pwd:
        log(f"credentials   : using stored '{label}' ({backend_name()}: {target}, user {user})")
        return user, pwd
    if _BACKEND is None:
        log(f"credentials   : no Credential Manager backend; prompting for '{label}'")
    else:
        log(f"credentials   : '{label}' not stored ({target}); prompting (store with "
            f"`python credential_store.py set {key}`)")
    prompt_user = default_username or ""
    suffix = f" [{prompt_user}]" if prompt_user else ""
    entered = input(f"** {label} username{suffix}: ").strip() or prompt_user
    pwd = getpass.getpass(f"** {label} password for {entered}: ")
    if allow_save and _BACKEND is not None and entered and pwd:
        ans = input(f"   Save these '{label}' credentials to Windows Credential Manager? [y/N]: ").strip().lower()
        if ans == "y":
            try:
                set_credential(target, entered, pwd)
                log(f"credentials   : saved '{label}' to {target}")
            except Exception as e:
                log(f"credentials   : could not save '{label}': {e}")
    return entered, pwd


def _arcpy_sign_in(portal_url, username, password, log):
    """arcpy.SignInToPortal so geoprocessing tools (arcpy) use the same login as the GIS object. Called
    only when connect(sign_in_arcpy=True). arcpy is imported lazily so scripts that only need GIS() never
    require it. FATAL: raises on failure (arcpy not importable, or the sign-in errors) so a script that
    depends on arcpy being authenticated stops here rather than silently running unauthenticated
    geoprocessing calls."""
    try:
        import arcpy
    except Exception as e:
        raise RuntimeError(f"sign_in_arcpy=True but arcpy could not be imported: {e}") from e
    try:
        arcpy.SignInToPortal(portal_url, username, password)
        log(f"connect       : arcpy signed in to {portal_url} as {username}")
    except Exception as e:
        raise RuntimeError(f"arcpy.SignInToPortal({portal_url}) failed: {e}") from e


def connect(portal_url, key=None, default_username="", allow_pro_fallback=True,
            allow_prompt_fallback=True, sign_in_arcpy=False, log=print, **gis_kwargs):
    """Connect to an ArcGIS portal (Enterprise OR ArcGIS Online) and return an authenticated
    arcgis.gis.GIS, reusing the stored Windows Credential Manager login when one is available.

    Shared by multiple arcgis/arcpy scripts so the connect-with-stored-credentials logic lives in one
    place. Auth precedence is CREDENTIALS FIRST -- deliberately NOT GIS("pro") first:
      1. resolve(): the stored credential for `key`, else an interactive prompt (which can offer to save
         it). `key` defaults to 'agol' for *.arcgis.com hosts, else 'portal' (override for 'GPUser' etc.).
      2. Fallback (only if step 1's login raises AND allow_pro_fallback): the active ArcGIS Pro session,
         but ONLY when it is signed in to this same portal host.
      3. Last resort (only if steps 1-2 fail AND allow_prompt_fallback): prompt for a username/password
         and try once more -- covers a stored credential that is wrong/expired, or a Pro session that
         isn't this portal -- then offer to save the working login for future unattended runs.

    sign_in_arcpy=True ALSO calls arcpy.SignInToPortal(portal_url, user, pwd) after a username/password
    login (steps 1 and 3), so geoprocessing tools share the same login -- for scripts that mix arcpy with
    the arcgis API (most scripts only need GIS() and can leave this False). FATAL: if the arcpy sign-in
    fails (arcpy not importable, or SignInToPortal errors) connect() raises, rather than returning a GIS
    whose arcpy half is unauthenticated. The Pro-session fallback (step 2) already provides arcpy with the
    active session, so it is not re-signed-in there. Extra **gis_kwargs (e.g. verify_cert=False) are passed
    through to the GIS(portal_url, ...) constructor.

    Set allow_pro_fallback=False / allow_prompt_fallback=False for a fully unattended run that must fail
    fast rather than block on a prompt. The 'arcgis' API is imported lazily here so importing
    credential_store for pure credential operations (the CLI, resolve(), get/set/delete) never requires
    arcgis to be installed. Raises if no connection can be made.
    """
    try:
        from arcgis.gis import GIS
    except Exception as e:
        raise RuntimeError("the 'arcgis' API is required to connect() but could not be imported") from e

    host = portal_url.split("//")[-1].split("/")[0].lower()
    if not key:
        key = "agol" if "arcgis.com" in host else "portal"

    # 1) Stored credential (else interactive prompt) -- the preferred, unattended-friendly path.
    user, pwd = resolve(key, f"Portal {portal_url} (not SSO)", default_username=default_username, log=log)
    if user and pwd:
        gis = None
        try:
            gis = GIS(portal_url, user, pwd, **gis_kwargs)
            log(f"connect       : connected to {portal_url} as {user}")
        except Exception as e:
            log(f"connect       : login to {portal_url} as {user} failed: {e}")
            if not allow_pro_fallback and not allow_prompt_fallback:
                raise
        if gis is not None:
            # Login succeeded. The arcpy sign-in is OUTSIDE the try above on purpose: when
            # sign_in_arcpy=True it is FATAL, so its failure must propagate -- not be caught as a
            # "login failed" and fall through to the Pro/prompt fallbacks.
            if sign_in_arcpy:
                _arcpy_sign_in(portal_url, user, pwd, log)
            return gis
    elif not allow_pro_fallback and not allow_prompt_fallback:
        raise RuntimeError(f"no usable credentials for {portal_url} (key '{key}')")

    # 2) Fallback only: the active ArcGIS Pro session, and only if it IS this portal.
    try:
        gis = GIS("pro")
        if gis.url and host in gis.url.lower() and gis.users.me:
            log(f"connect       : using active ArcGIS Pro session: {gis.url}")
            return gis
        log(f"connect       : active Pro session ({getattr(gis, 'url', None)}) is not {portal_url}; not used")
    except Exception as e:
        log(f"connect       : ArcGIS Pro session not usable: {e}")

    # 3) Last resort: prompt for a username/password and try once more. Reached when a stored credential
    #    is wrong/expired (so step 1's login raised) and the Pro session didn't apply. On success, offer
    #    to save the working credential to the Credential Manager so the next run is unattended.
    if allow_prompt_fallback:
        log(f"connect       : prompting for {portal_url} credentials (previous attempts failed)")
        suffix = f" [{default_username}]" if default_username else ""
        entered = input(f"** Portal username for {portal_url} (not SSO){suffix}: ").strip() or default_username
        if entered:
            pwd2 = getpass.getpass(f"** Portal password for {entered}: ")
            if pwd2:
                gis = None
                try:
                    gis = GIS(portal_url, entered, pwd2, **gis_kwargs)
                    log(f"connect       : connected to {portal_url} as {entered} (prompted)")
                except Exception as e:
                    log(f"connect       : prompted login to {portal_url} as {entered} failed: {e}")
                if gis is not None:
                    # arcpy sign-in is OUTSIDE the login try: when sign_in_arcpy=True it is FATAL and
                    # must propagate rather than be swallowed as a login failure.
                    if sign_in_arcpy:
                        _arcpy_sign_in(portal_url, entered, pwd2, log)
                    if _BACKEND is not None:
                        try:
                            ans = input(f"   Save these credentials to Windows Credential Manager "
                                        f"({_target(key)})? [y/N]: ").strip().lower()
                            if ans == "y":
                                set_credential(_target(key), entered, pwd2)
                                log(f"connect       : saved credentials to {_target(key)}")
                        except Exception as e:
                            log(f"connect       : could not save credentials: {e}")
                    return gis

    raise RuntimeError(f"could not connect to {portal_url} via stored/prompted credentials or a Pro session")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def _cli():
    args = sys.argv[1:]
    if not args or args[0] not in ("set", "get", "delete", "list"):
        print(__doc__)
        print(f"backend: {backend_name()}")
        return
    cmd = args[0]
    if cmd == "list":
        ts = list_targets()
        print(f"backend: {backend_name()}")
        print("stored migration credentials:" if ts else "no stored migration credentials found")
        for t in ts:
            u, _ = get_credential(t)
            print(f"  {t}  (user: {u})")
        return
    if len(args) < 2 or args[1] not in TARGETS:
        print(f"usage: python credential_store.py {cmd} <{'|'.join(TARGETS)}>")
        return
    key = args[1]
    target = _target(key)
    if cmd == "set":
        if _BACKEND is None:
            print("no Credential Manager backend available (win32cred/keyring). Cannot store.")
            return
        default_user = {"GPUser": "GPUser"}.get(key, "")
        suffix = f" [{default_user}]" if default_user else ""
        user = input(f"{key} username{suffix}: ").strip() or default_user
        pwd = getpass.getpass(f"{key} password for {user}: ")
        if not user or not pwd:
            print("username and password are both required; nothing stored.")
            return
        set_credential(target, user, pwd)
        print(f"stored '{key}' -> {target} (user: {user})")
    elif cmd == "get":
        u, p = get_credential(target)
        if u:
            print(f"{key} -> {target}: user '{u}', password {'***set***' if p else '(none)'}")
        else:
            print(f"{key} -> {target}: not stored")
    elif cmd == "delete":
        print(f"deleted '{key}'" if delete_credential(target) else f"'{key}' not found / not deleted")


if __name__ == "__main__":
    _cli()
