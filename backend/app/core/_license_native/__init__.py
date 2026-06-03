try:
    from ._verify import verify_license_core
    USE_NATIVE_VERIFY = True
except ImportError:
    USE_NATIVE_VERIFY = False
