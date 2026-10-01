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

## Console tabs

Ten tabs, none holding more than two cards. Any tab is addressable with
`?tab=<id>` so another page can send the operator straight to the setting that
is blocking them (`/settings?tab=sermonaudio` from a refused publish). The
pre-existing `?cloud=connected` link still resolves to the Cloud Mounts tab.

| Tab id | Label | Cards |
|---|---|---|
| `general` | General | General, Processing defaults |
| `processing` | Audio & Transcription | Audio settings, Transcription settings |
| `llm` | LLM Providers | LLM connections, Routing |
| `sermonaudio` | SermonAudio | Accounts, Single-account fallback, Upload routing |
| `cloud` | Cloud Mounts | Cloud mounts |
| `content` | Descriptions & Prompts | Validation, Prompt templates |
| `backup` | Backup & Restore | Full data backup |
| `account` | Appearance & Account | Theme, Display name, Password reset |
| `users` | Users | User administration (admin only) |
| `system` | System | Front-door state, the server's own report, Log level (admin only) |

## Legacy tab map

| Legacy tab | Legacy control (config path) | Console home |
|---|---|---|
| General | API Key (`api_key`) | SermonAudio tab, per-account `api_key`; Single-account fallback for the seeded/env value |
| General | Broadcaster ID (`broadcaster_id`) | SermonAudio tab, per-account `broadcaster_id`; Single-account fallback for the seeded/env value |
| General | Test API Connection | Removed (see below) |
| General | Dry Run Mode (`dry_run`) | General |
| General | Debug Mode (`debug`) | General |
| General | Hashtag Verification (`hashtag_verification`) | General |
| General | Output Directory (`output_directory`) | General, per-user `settings.general.output_dir` |
| General | Save Original Audio (`save_original_audio`) | General |
| General | Save Transcript (`save_transcript`) | General |
| LLM | Primary Provider (`llm.primary.*`) | LLM Providers, Primary slot |
| LLM | Fallback Provider (`llm.fallback.*`) | LLM Providers, Fallback slot |
| LLM | Validator Provider (`llm.validator.*`) | LLM Providers, Validator slot |
| LLM | Test provider connection | LLM Providers, "Test connection" |
| Embeddings | Primary provider (`embeddings.primary.*`) | Removed (see below) |
| Embeddings | Fallback providers (`embeddings.fallback`) | Removed (see below) |
| Audio | Enhancement Method (`audio_enhancement_method`) | Audio & Transcription |
| Audio | Custom HF Repo (`clear_custom_repo`) | Audio & Transcription, custom method |
| Audio | Custom ONNX file (`clear_custom_file`) | Audio & Transcription, custom method |
| Audio | Enhancement Device (`enhancement.device`) | Audio & Transcription |
| Audio | Noise Reduction (`audio_noise_reduction`) | Audio & Transcription |
| Audio | Audio Amplification (`audio_amplify`) | Audio & Transcription |
| Audio | Audio Normalization (`audio_normalize`) | Audio & Transcription |
| Audio | Gain dB (`audio_gain_db`) | Audio & Transcription |
| Audio | Target Level dB (`audio_target_level_db`) | Audio & Transcription |
| Audio | Process Audio (`metadata_processing.process_audio`) | Audio & Transcription, legacy boolean, ignored when it conflicts with the enhancement method |
| Transcription | Backend (`transcription.backend`) | Audio & Transcription |
| Transcription | Local Model (`transcription.<local>.model`) | Audio & Transcription, local backends |
| Transcription | Device (`transcription.<local>.device`) | Audio & Transcription, local backends |
| Transcription | Compute Type (`transcription.compute_type`) | Audio & Transcription, local backends |
| Transcription | Language (`transcription.<local>.language`) | Audio & Transcription, local backends |
| Transcription | OpenAI API Key (`transcription.whisper_openai.api_key`) | Audio & Transcription, OpenAI backend |
| Transcription | OpenAI Base URL (`transcription.whisper_openai.base_url`) | Audio & Transcription, OpenAI backend |
| Transcription | OpenAI Model (`transcription.whisper_openai.model`) | Audio & Transcription, OpenAI backend |
| Validation | Enable Description Validation (`metadata_processing.description.validation.enabled`) | Descriptions & Prompts |
| Validation | Validation criteria (`metadata_processing.description.validation.criteria`) | Descriptions & Prompts |
| Validation | Description Update if Missing (`metadata_processing.description.update_if_missing`) | Descriptions & Prompts |
| Validation | Description Update if Minimal (`metadata_processing.description.update_if_minimal`) | Descriptions & Prompts |
| Validation | Description Min Length (`metadata_processing.description.min_length_threshold`) | Descriptions & Prompts |
| Validation | Hashtag Update if Missing (`metadata_processing.hashtags.update_if_missing`) | Descriptions & Prompts |
| Validation | Hashtag Update if Minimal (`metadata_processing.hashtags.update_if_minimal`) | Descriptions & Prompts |
| Validation | Hashtag Min Length (`metadata_processing.hashtags.min_length_threshold`) | Descriptions & Prompts |
| Advanced | YAML Backup & Restore (export/import `config.yaml`) | Backup & Restore (JSON full-data backup) |
| Advanced | Reset to Defaults | Backup & Restore, "Reset to defaults" |
| Advanced | SQL Config Manager (edit/import/export/history) | Backup & Restore, config sections read and write the same `config_cache` row |
| Templates | Title Generation (`prompt_templates.title`) | Descriptions & Prompts, Prompt templates |
| Templates | Short Title Generation (`prompt_templates.short_title`) | Descriptions & Prompts, Prompt templates |
| Templates | Description Generation (`prompt_templates.description`) | Descriptions & Prompts, Prompt templates |
| Templates | Hashtag Generation (`prompt_templates.hashtags`) | Descriptions & Prompts, Prompt templates |
| Templates | Hashtag Verification (`prompt_templates.hashtag_verification`) | Descriptions & Prompts, Prompt templates |
| Templates | Description Validation (`prompt_templates.description_validation`) | Descriptions & Prompts, stored but no pipeline consumer |

## Console sections with no legacy equivalent

The console adds sections the Streamlit page never had. They are new product
surface, not migrations.

| Console section | Purpose |
|---|---|
| SermonAudio Accounts | Multiple broadcaster accounts with a default, replacing the single legacy `api_key` plus `broadcaster_id` pair |
| Single-account fallback | The seeded/env `api_key` and `broadcaster_id` the pipeline uses when no account is picked, with its winning source named (`db` / env / `default`) |
| Cloud Mounts | Remote upload targets |
| Routing (inside LLM Providers) | Which provider slot handles metadata, validation, transcription assist, and fallback |
| Processing defaults (inside General) | Keeper audio and video bitrates, default audio offset |
| Appearance (inside Appearance & Account) | Theme |
| Account (inside Appearance & Account) | Display name, password reset |
| Users | Admin account management |
| System | Front-door state, the server's own `/api/status` report, log level |

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
`default`). The SermonAudio tab renders this in its "Upload routing"
card, so the operator can see which account an upload will use without
revealing the key.

## Service health states

`GET /api/status` resolves the same app config the pipeline resolves, through
`ui.config_utils`, so it reports the values a run would actually use. It reports
three states for the operator: `ok`, `warning`, and `unknown`. A check that
could not determine its state reports `unknown`; an unreadable gauge is not a
warning. Every non-`ok` entry carries the Settings tab that fixes it, appended to
its `details` by `ui.system_status.with_remediation`.

An install whose users have stored SermonAudio accounts reports the API as
connected even with no install-wide credential, because an upload uses the
account of the signed-in user. A fallback LLM provider is optional, so an empty
fallback slot reports `ok`, not a fault.

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
