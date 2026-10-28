# Settings parity: Streamlit UI to web console

The Streamlit settings page (`ui/ui_pages/settings.py`) had eight tabs before
the embeddings removal, leaving seven. The web
console (`web/src/pages/Settings.tsx`) is the replacement front end. This
document maps every legacy control to its console home, and names what was
deliberately dropped.

The console writes through `server/api/routers/app_config.py` into the settings
database (`config_cache.app_config`), which is the layer the processing
pipeline resolves. `src/core/config.py::ENV_CONFIG_MAP` remains the only
enumeration of environment variables.

## Legacy tab map

| Legacy tab | Legacy control (config path) | Console home |
|---|---|---|
| General | API Key (`api_key`) | SermonAudio Accounts, per-account `api_key`; Single-account fallback for the seeded/env value |
| General | Broadcaster ID (`broadcaster_id`) | SermonAudio Accounts, per-account `broadcaster_id`; Single-account fallback for the seeded/env value |
| General | Test API Connection | Removed (see below) |
| General | Dry Run Mode (`dry_run`) | General |
| General | Debug Mode (`debug`) | General |
| General | Hashtag Verification (`hashtag_verification`) | General |
| General | Output Directory (`output_directory`) | General, per-user `settings.general.output_dir`; Storage holds the deployment root |
| General | Save Original Audio (`save_original_audio`) | General |
| General | Save Transcript (`save_transcript`) | General |
| LLM | Primary Provider (`llm.primary.*`) | LLM Providers, Primary slot |
| LLM | Fallback Provider (`llm.fallback.*`) | LLM Providers, Fallback slot |
| LLM | Validator Provider (`llm.validator.*`) | LLM Providers, Validator slot |
| LLM | Test provider connection | LLM Providers, "Test connection" |
| Embeddings | Primary provider (`embeddings.primary.*`) | Removed (see below) |
| Embeddings | Fallback providers (`embeddings.fallback`) | Removed (see below) |
| Audio | Enhancement Method (`audio_enhancement_method`) | Audio |
| Audio | Custom HF Repo (`clear_custom_repo`) | Audio, custom method |
| Audio | Custom ONNX file (`clear_custom_file`) | Audio, custom method |
| Audio | Enhancement Device (`enhancement.device`) | Audio |
| Audio | Noise Reduction (`audio_noise_reduction`) | Audio |
| Audio | Audio Amplification (`audio_amplify`) | Audio |
| Audio | Audio Normalization (`audio_normalize`) | Audio |
| Audio | Gain dB (`audio_gain_db`) | Audio |
| Audio | Target Level dB (`audio_target_level_db`) | Audio |
| Audio | Process Audio (`metadata_processing.process_audio`) | Audio, legacy boolean, ignored when it conflicts with the enhancement method |
| Transcription | Backend (`transcription.backend`) | Transcription |
| Transcription | Local Model (`transcription.<local>.model`) | Transcription, local backends |
| Transcription | Device (`transcription.<local>.device`) | Transcription, local backends |
| Transcription | Compute Type (`transcription.compute_type`) | Transcription, local backends |
| Transcription | Language (`transcription.<local>.language`) | Transcription, local backends |
| Transcription | OpenAI API Key (`transcription.whisper_openai.api_key`) | Transcription, OpenAI backend |
| Transcription | OpenAI Base URL (`transcription.whisper_openai.base_url`) | Transcription, OpenAI backend |
| Transcription | OpenAI Model (`transcription.whisper_openai.model`) | Transcription, OpenAI backend |
| Validation | Enable Description Validation (`metadata_processing.description.validation.enabled`) | Validation |
| Validation | Validation criteria (`metadata_processing.description.validation.criteria`) | Validation |
| Validation | Description Update if Missing (`metadata_processing.description.update_if_missing`) | Validation |
| Validation | Description Update if Minimal (`metadata_processing.description.update_if_minimal`) | Validation |
| Validation | Description Min Length (`metadata_processing.description.min_length_threshold`) | Validation |
| Validation | Hashtag Update if Missing (`metadata_processing.hashtags.update_if_missing`) | Validation |
| Validation | Hashtag Update if Minimal (`metadata_processing.hashtags.update_if_minimal`) | Validation |
| Validation | Hashtag Min Length (`metadata_processing.hashtags.min_length_threshold`) | Validation |
| Advanced | YAML Backup & Restore (export/import `config.yaml`) | Backup & Restore (JSON full-data backup) |
| Advanced | Reset to Defaults | Backup & Restore, "Reset to defaults" |
| Advanced | SQL Config Manager (edit/import/export/history) | Backup & Restore, config sections read and write the same `config_cache` row |
| Templates | Title Generation (`prompt_templates.title`) | Prompt Templates |
| Templates | Short Title Generation (`prompt_templates.short_title`) | Prompt Templates |
| Templates | Description Generation (`prompt_templates.description`) | Prompt Templates |
| Templates | Hashtag Generation (`prompt_templates.hashtags`) | Prompt Templates |
| Templates | Hashtag Verification (`prompt_templates.hashtag_verification`) | Prompt Templates |
| Templates | Description Validation (`prompt_templates.description_validation`) | Prompt Templates, stored but no pipeline consumer |

## Console sections with no legacy equivalent

The console adds sections the Streamlit page never had. They are new product
surface, not migrations.

| Console section | Purpose |
|---|---|
| SermonAudio Accounts | Multiple broadcaster accounts with a default, replacing the single legacy `api_key` plus `broadcaster_id` pair |
| Single-account fallback | The seeded/env `api_key` and `broadcaster_id` the pipeline uses when no account is picked, with its winning source named (`db` / env / `default`) |
| Cloud Mounts | Remote upload targets |
| Routing (inside LLM Providers) | Which provider slot handles metadata, validation, transcription assist, and fallback |
| Processing defaults | Keeper audio and video bitrates, default audio offset |
| Resources | Job queue RAM/VRAM floors and the enhancement GPU threshold. Admin only. |
| Storage | Input, upload, temp, review-media, and trash roots plus trash retention. Admin only. || Appearance | Theme |
| Account | Display name, password reset |
| Users | Admin account management |
| System | Front-door cutover state and log level |

## Deliberate removals

- **Embeddings and RAG (owner decision, feature removed).** The legacy
  Embeddings tab configured `embeddings.primary.*` and a fallback list for the
  analytics RAG system. The feature was removed in full: the modules
  (`ui/embedding_manager.py`, `ui/rag_system.py`, `ui/analytics_chat.py`), the
  Streamlit tab, the Analytics chat interface, the `embeddings` and
  `rag_system` config blocks, the `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL`
  environment variables, the `chromadb` and `sentence-transformers`
  dependencies, and the `analytics_cache` / `analytics_vector_db` data
  directories. There is no console section to map to because the surface is
  gone, not deferred.
- **YAML config file import/export in the UI.** The console backup is a JSON
  full-data backup, not a `config.yaml` round trip. The legacy one-time import
  of an existing `config.yaml` into an empty database still happens at
  resolution time.
- **Model download manager.** The legacy Transcription tab offered a sentence
  transformer download helper. Whisper weights are fetched inside the
  processing container on first use, and the console states that limitation
  instead of offering a mock download button.
- **Test API Connection.** The legacy General tab had a button that called the
  SermonAudio API with the saved credentials. The console has no server-side
  credential check endpoint, so the button was removed rather than kept as a
  fake success path. Credentials are exercised for real when a sermon uploads.

## Audio settings reach the pipeline

The five audio settings (`audio_noise_reduction`, `audio_amplify`,
`audio_normalize`, `audio_gain_db`, `audio_target_level_db`) resolve through
`audio_processing_settings` in `sermon_updater.py` and are passed as keyword
arguments to `AudioProcessor.process_sermon_audio` on the enhancement call. A
fresh run and the Library apply path use the same resolver, so a value saved on
the console Audio section reaches the enhancer.

`audio_enhancement_method == "none"` means skip on every path. It wins over the
legacy `metadata_processing.process_audio` boolean, and when the two disagree the
log names the winner and the losing value once per resolution.

## Per-user upload routing

The credentials a publish uses are the ones belonging to the user who owns the
job. The pipeline resolves them at job-execution time (never at enqueue time)
from that user's `connections.sermonaudio` setting in `user_settings`: the
account they marked as default, or the first usable account they own when no
default is set. The job's resolved config is rebound to those credentials
before the engine runs, so a job can never publish as another user.

The Single-account fallback (the seeded/env `api_key` and `broadcaster_id`)
applies only while no user has stored a connection anywhere. Once any account
exists, a user without one resolves to an empty credential and the publish is
refused with "Connect your SermonAudio account in Settings before publishing."
The console refuses before a job is queued, and the executor refuses as a
second line of defence. A dry run, a local render, and an interactive
auto-edit pass that stops for review are never blocked; the gate applies when
the job actually publishes.

`GET /api/me/sermonaudio-connection` returns the resolved connection for the
current user as `configured`, `source`, `account_name`, `broadcaster_id`,
`masked_key`, and the refusal `message`. `source` is `user` for the user's own
account, or the winning fallback source (an environment variable name, `db`, or
`default`). The SermonAudio Accounts page renders this in its "Upload routing"
card, so the operator can see which account an upload will use without
revealing the key.

## Environment override display

Every console config field reads its winning source from
`GET /api/config/sections/{section}`. When an environment variable supplies a
value, the field shows a badge with that variable name; `db` and `default`
sources show no badge. This is the visible form of the rule that the
environment always overrides saved settings. The Single-account fallback card
goes further and spells out `set by environment: <VAR>` for each SermonAudio
credential, so an operator can see why editing the saved value has no effect
until the variable is unset.

## Related

- `docs/INSTALLATION_GUIDE.md` for the database-authoritative configuration model.
- `src/core/config.py::ENV_CONFIG_MAP` for the environment variable enumeration.

## Full resolved-leaf inventory (phase 10A)

The legacy map above is not the whole resolver surface. `config/templates/*.yaml`
and `src/core/config.py::ENV_CONFIG_MAP` carry more leaves than the Streamlit
page ever exposed. `tests/unit/test_settings_parity.py` flattens every template,
the canonical example config, and the environment map, then requires each non-LLM
leaf to appear in one of three places: a console `SECTIONS` entry, the retired
list, or the template-only list. A new key cannot arrive silently.

### Editable in the console

| Section | Key | Console home |
|---|---|---|
| general | `dry_run`, `debug`, `hashtag_verification`, `save_original_audio`, `save_transcript` | General |
| general | `output_directory` | Storage (deployment root) and General (per-user default) |
| audio | `audio_enhancement_method`, `enhancement.device`, `clear_custom_repo`, `clear_custom_file` | Audio |
| audio | `audio_noise_reduction`, `audio_amplify`, `audio_normalize`, `audio_gain_db`, `audio_target_level_db` | Audio |
| audio | `preprocess_noise_gate` | Audio, Advanced; off by default because it harmed speech |
| audio | `metadata_processing.process_audio` | Audio, Advanced; legacy boolean, loses to an explicit enhancement method |
| resources | `enhancement.min_gpu_vram_gb`, `job_queue.min_free_ram_gb`, `job_queue.min_free_vram_gb` | Resources, admin only |
| storage | `input_directory`, `output_directory`, `upload_dir`, `processing_temp_dir`, `review_media_directory`, `trash_directory`, `trash_retention_days` | Storage, admin only |
| transcription | `transcription.backend`, `transcription.compute_type` | Transcription |
| transcription | `transcription.whisper_local.{model,device,language}` | Transcription, local backends |
| transcription | `transcription.faster_whisper_local.{model,device,compute_type,language}` | Transcription, local backends |
| transcription | `transcription.whisper_openai.{base_url,model,api_key}` | Transcription, OpenAI backend |
| validation | `metadata_processing.enabled` | Validation, "Generate metadata" |
| validation | `metadata_processing.description.validation.{enabled,criteria}` | Validation |
| validation | `metadata_processing.description.{update_if_missing,update_if_minimal,min_length_threshold}` | Validation |
| validation | `metadata_processing.hashtags.{update_if_missing,update_if_minimal,min_length_threshold}` | Validation |
| prompts | `prompt_templates` | Prompt Templates |
| sermonaudio | `api_key`, `broadcaster_id` | Single-account fallback |
| llm | `llm.<slot>.<provider>.*` | LLM Providers, including the Ollama `think` toggle |

### Retired keys

| Key | Reason |
|---|---|
| `metadata_processing.description.force_update` | A per-run batch option read from job parameters, not the resolved config. |
| `metadata_processing.hashtags.force_update` | Same per-run batch option. |
| `verbose` | CLI per-run flag. Console jobs report progress through job logs. |

### Template or environment only

These leaves stay operator-managed through the variant template or an
environment variable. They are either per-run choices made on another page or
deployment plumbing that needs a restart.

| Key | Reason |
|---|---|
| `auto_edit.enabled`, `auto_edit.mode`, `auto_edit.fade_to_black`, `auto_edit.logo_path` | Per-run switches on the new-teaching form; the template sets the default. |
| `auto_edit.auto_confidence_threshold`, `auto_edit.qa_margin_seconds`, `auto_edit.min_sermon_seconds`, `auto_edit.require_review` | Auto-edit tuning, template-managed. |
| `auto_edit.logo_hold`, `auto_edit.fade_out_tail_seconds` | Auto-edit tuning, template-managed. |
| `auto_edit.keeper.*` | Keeper transcode policy and tuning. Deletion still routes through trash. |
| `ingest_watcher.*` | The watcher starts from `INGEST_WATCHER_ENABLED`; Signal credentials come from `INGEST_SIGNAL_URL`, `INGEST_SIGNAL_SENDER`, `INGEST_SIGNAL_RECIPIENTS`. |
| `transcription.whisper_local.compute_type` | Torch whisper ignores it; faster-whisper owns `compute_type`. |

`web_console_ready` lives in the same settings database but is not a resolved
pipeline leaf. `GET /api/meta/retirement` reports it, and the System card names
the cutover steps. It stays out of the config sections so a routine settings
save cannot flip the front door.
