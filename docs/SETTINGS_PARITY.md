# Settings parity: Streamlit UI to web console

The Streamlit settings page (`ui/ui_pages/settings.py`) had eight tabs. The web
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
| General | API Key (`api_key`) | SermonAudio Accounts, per-account `api_key` |
| General | Broadcaster ID (`broadcaster_id`) | SermonAudio Accounts, per-account `broadcaster_id` |
| General | Test API Connection | SermonAudio Accounts, "Test" |
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
| Audio | Enhancement Method (`audio_enhancement_method`) | Audio |
| Audio | Custom HF Repo (`clear_custom_repo`) | Audio, custom method |
| Audio | Custom ONNX file (`clear_custom_file`) | Audio, custom method |
| Audio | Enhancement Device (`enhancement.device`) | Audio |
| Audio | Noise Reduction (`audio_noise_reduction`) | Audio |
| Audio | Audio Amplification (`audio_amplify`) | Audio |
| Audio | Audio Normalization (`audio_normalize`) | Audio |
| Audio | Gain dB (`audio_gain_db`) | Audio |
| Audio | Target Level dB (`audio_target_level_db`) | Audio |
| Transcription | Backend (`transcription.backend`) | Transcription |
| Transcription | Local Model (`transcription.<local>.model`) | Transcription, local backends |
| Transcription | Device (`transcription.<local>.device`) | Transcription, local backends |
| Transcription | Compute Type (`transcription.compute_type`) | Transcription, local backends |
| Transcription | Language (`transcription.<local>.language`) | Transcription, local backends |
| Transcription | OpenAI API Key (`transcription.whisper_openai.api_key`) | Transcription, OpenAI backend |
| Transcription | OpenAI Base URL (`transcription.whisper_openai.base_url`) | Transcription, OpenAI backend |
| Transcription | OpenAI Model (`transcription.whisper_openai.model`) | Transcription, OpenAI backend |
| Transcription | OpenRouter API Key (`transcription.whisper_openrouter.api_key`) | Transcription, OpenRouter backend |
| Transcription | OpenRouter Base URL (`transcription.whisper_openrouter.base_url`) | Transcription, OpenRouter backend |
| Transcription | OpenRouter Model (`transcription.whisper_openrouter.model`) | Transcription, OpenRouter backend |
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
| Cloud Mounts | Remote upload targets |
| Routing (inside LLM Providers) | Which provider slot handles metadata, validation, transcription assist, and fallback |
| Processing defaults | Keeper audio and video bitrates, default audio offset |
| Appearance | Theme |
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

## Environment override display

Every console config field reads its winning source from
`GET /api/config/sections/{section}`. When an environment variable supplies a
value, the field shows a badge with that variable name; `db` and `default`
sources show no badge. This is the visible form of the rule that the
environment always overrides saved settings.

## Related

- `docs/INSTALLATION_GUIDE.md` for the database-authoritative configuration model.
- `src/core/config.py::ENV_CONFIG_MAP` for the environment variable enumeration.
