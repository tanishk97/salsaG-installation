"""
Drop-in logging-based observability for SalsaGate.
- Structured JSON logs via python-json-logger
- Ships to CloudWatch Logs via watchtower
- Embedded Metric Format (EMF) helper for alerts
"""
import os, time, logging, json, socket, uuid, boto3

from logging.handlers import SysLogHandler

try:
    import watchtower
    from pythonjsonlogger import jsonlogger
except Exception as e:
    raise RuntimeError("Missing deps: pip install watchtower python-json-logger") from e


_ENV      = os.getenv("ENV", "dev")
_SERVICE  = os.getenv("SERVICE", "salsagate-cli")
_VERSION  = os.getenv("VERSION", "0.0.1")
_GIT_SHA  = os.getenv("GIT_SHA")
_HOST     = socket.gethostname()
#_STREAM   = f"{_HOST}-{_SERVICE}"
#_LOGGROUP = os.getenv("LOG_GROUP", f"/salsagate/{_ENV}/app")


class ContextFilter(logging.Filter):
    def filter(self, record):
        # Inject stable fields
        record.service_name = _SERVICE
        record.service_version = _VERSION
        record.deployment_environment = _ENV
        record.git_sha = _GIT_SHA
        record.host = _HOST
        return True

_root = logging.getLogger("salsagate")


def initialize_logger(log_cfg=None):


    if not log_cfg:
        return False
    
    #clear any app owned handlers in case of reinit
    for h in list(_root.handlers):
        if getattr(h, "_salsag_owned", False):
            _root.removeHandler(h)

    #clear any app owned filters in case of reinit
    for f in list(_root.filters): 
        if getattr(f, "_salsag_owned", False):
            _root.removeFilter(f)

    # Reset level
    _root.setLevel(logging.INFO)
    _root.propagate = False

    
    # CloudWatch Handler

    if "cloudwatch" in log_cfg:
        log_group = os.getenv("LOG_GROUP", log_cfg["cloudwatch"].get("log_group")) or f"/salsagate/{_ENV}/app"
        stream_name = log_cfg["cloudwatch"].get("stream_name")
        cw_log_level_value =  log_cfg["cloudwatch"].get("level")
        cw_region_name = log_cfg["cloudwatch"].get("region")
        
        cloudwatch_client = boto3.client("logs", region_name=cw_region_name)

        cw_handler = watchtower.CloudWatchLogHandler(
            log_group=log_group,
            stream_name=stream_name,
            boto3_client=cloudwatch_client,
            create_log_group=True,
            use_queues=True,
        )
        cw_handler._salsag_owned = True
        cw_handler.setFormatter(jsonlogger.JsonFormatter())
        cw_handler.setLevel(cw_log_level_value)
        _root.addHandler(cw_handler)

    # Syslog Handler
    if "syslog" in log_cfg:
        syslog_addr = log_cfg["syslog"].get("address", "/dev/log")
        syslog_log_level_value =  log_cfg["cloudwatch"].get("level")
        syslog_handler = logging.handlers.SysLogHandler(address=syslog_addr)
        syslog_handler._salsag_owned = True
        syslog_handler.setFormatter(jsonlogger.JsonFormatter())
        syslog_handler.setLevel(syslog_log_level_value)
        _root.addHandler(syslog_handler)

    # Always add contextual info
    filter = ContextFilter()
    filter._salsag_owned = True
    _root.addFilter(filter)



def get_logger(name: str):
    return _root.getChild(name)

def metric_count(name: str, dims=None, count: int = 1):
    """Emit a Count metric using CloudWatch EMF in the SalsaGate namespace."""
    if dims is None: dims = {}
    payload = {
        "message": f"metric {name}",
        "service.name": _SERVICE,
        "service.version": _VERSION,
        "deployment.environment": _ENV,
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "SalsaGate",
                "Dimensions": [sorted(list(dims.keys())) or ["service.name","deployment.environment"]],
                "Metrics": [{"Name": name, "Unit": "Count"}],
            }],
        },
        name: count,
    }
    # Include dims at top-level for queryability
    for k,v in dims.items():
        payload[k] = v
    _root.info(payload)

class log_step:
    """Context manager to log start/duration/outcome for a pipeline step."""
    def __init__(self, step_name: str, **kv):
        self.step_name = step_name
        self.kv = kv
        self._start = None

    def __enter__(self):
        self._start = time.time()
        _root.info({
            "event.name": self.step_name,
            "event.phase": "start",
            **self.kv,
        })
        return self

    def __exit__(self, exc_type, exc, tb):
        duration_ms = int((time.time() - self._start) * 1000)
        payload = {
            "event.name": self.step_name,
            "event.phase": "end",
            "duration_ms": duration_ms,
            **self.kv,
        }
        if exc:
            payload["outcome"] = "failure"
            payload["error.type"] = getattr(exc, "__class__", type(exc)).__name__
            payload["error.message"] = str(exc)
            _root.error(payload)
        else:
            payload["outcome"] = "success"
            _root.info(payload)
        # Do not suppress exceptions
        return False