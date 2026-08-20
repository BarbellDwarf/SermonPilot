# Performance Monitoring

SermonPilot ships a performance monitor in `ui/performance_monitor.py`. It
collects live system metrics, reads processing statistics from the SQLite
database, and produces optimization recommendations. The Streamlit Analytics
page surfaces the same data in the "⚡ Performance" tab.

## What it measures

### System metrics

`PerformanceMonitor.get_system_metrics()` returns a dict with these keys:

- `cpu`: `usage_percent`, `count`, `frequency_mhz`, `load_average`
- `memory`: `total_gb`, `available_gb`, `used_percent`, `swap_used_percent`
- `disk`: `total_gb`, `free_gb`, `used_percent`, `read_mb_per_sec`, `write_mb_per_sec`
- `network`: `bytes_sent_mb`, `bytes_recv_mb`, `packets_sent`, `packets_recv`
- `gpu`: `available`, `usage_percent`, `memory_used_gb`, `memory_total_gb`, `memory_percent`, `temperature_c`, `name`
- `timestamp`: Unix time of the sample

CPU, memory, disk, and network numbers come from `psutil`. GPU metrics come
from `nvidia-smi` when it is present on the system; if that fails, the
monitor falls back to `torch.cuda` detection, which reports only the device
name and total memory.

### Processing metrics

`PerformanceMonitor.get_processing_metrics()` reads three tables from the
SQLite database (`sermon_processor.db` by default): `processing_info`,
`validation_results`, and `background_jobs`. It returns:

- `total_processed`: rows in `processing_info`
- `success_rate` and `error_rate`: derived from `validation_results` when present
- `avg_processing_time` and `processing_times`: from `processing_info.processing_duration`
- `queue_length`, `pending_jobs`, `running_jobs`: from `background_jobs` in the last 7 days
- `validation_score_avg`: average `validation_results.score`

If the database or tables are missing, the method returns zeroed values
rather than raising.

### Optimization recommendations

`get_optimization_recommendations(system_metrics, processing_metrics)`
applies fixed thresholds to the two metric dicts and returns a list of
recommendations. Each entry has `title`, `priority`, `description`,
`impact`, and `effort` keys. The checks are:

- CPU usage above 80 percent
- Memory usage above 85 percent
- GPU unavailable with average processing time above 5 minutes
- GPU memory above 90 percent
- Error rate above 10 percent
- Average processing time above 10 minutes
- Disk usage above 90 percent
- Queue length above 50

A final entry reports that the system is running optimally when CPU usage is
below 50 percent, memory usage below 70 percent, and the error rate below
5 percent.

## Configuration

The monitor reads no configuration block and no config keys. The class
constructor takes an optional `db_path` argument that defaults to
`sermon_processor.db` in the current working directory.

## Usage

### From Python

```python
from ui.performance_monitor import PerformanceMonitor

monitor = PerformanceMonitor()

system = monitor.get_system_metrics()
print(f"CPU: {system['cpu']['usage_percent']}%")
print(f"Memory: {system['memory']['used_percent']}%")
print(f"GPU: {system['gpu']['name']}")

processing = monitor.get_processing_metrics()
print(f"Processed: {processing['total_processed']}")
print(f"Success rate: {processing['success_rate']:.1f}%")
print(f"Avg processing time: {processing['avg_processing_time']:.1f} minutes")

recommendations = monitor.get_optimization_recommendations(system, processing)
for rec in recommendations:
    print(f"[{rec['priority']}] {rec['title']}: {rec['description']}")
```

### From the UI

```bash
streamlit run streamlit_app.py
```

Open the Analytics page and switch to the "⚡ Performance" tab. The page
calls the module-level `get_comprehensive_performance_data()` function in
`ui/performance_monitor.py`, which combines the system metrics, processing
metrics, and recommendations into a single dict for display.

`get_comprehensive_performance_data()` returns:

- `avg_processing_time`, `processing_time_change`
- `success_rate`, `success_rate_change`
- `queue_length`, `queue_change`
- `error_rate`, `error_rate_change`
- `step_performance`: per-stage rows (step, avg_time, success_rate, bottleneck_score)
- `resource_usage`: `cpu_usage`, `memory_usage`, `disk_usage`, `network_io`, `gpu_usage`, `gpu_memory`
- `recommendations`: the list from `get_optimization_recommendations`
- `system_details` and `processing_details`: the raw metric dicts

The `step_performance` values are static placeholders in the code, not
measured per-sermon times.

## GPU data

The monitor queries NVIDIA GPUs with:

```bash
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name --format=csv,noheader,nounits
```

`nvidia-smi` must be on the `PATH` of the process running the monitor. In the
Docker image this requires an image built for the `cuda` backend and the
NVIDIA Container Toolkit on the host. Without `nvidia-smi` or a CUDA-capable
torch, `gpu.available` is `False` and the remaining GPU fields are zeroed.

## Troubleshooting

**`gpu.available` is always False.** Run `nvidia-smi` in the same
environment as the app. Inside the container: `docker compose exec sermon-pilot nvidia-smi`.

**Processing metrics are all zeros.** The monitor could not read
`processing_info`, `validation_results`, or `background_jobs`. Confirm the
database exists and has been populated by processing sermons. The monitor
defaults to `sermon_processor.db` in the working directory; if the app runs
from another directory, pass an explicit `db_path`.

**ImportError on `psutil`.** `psutil` is a declared dependency in
`pyproject.toml`. Reinstall with `uv sync` or
`uv pip install -r requirements/requirements.txt`.
