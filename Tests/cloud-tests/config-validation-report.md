# SermonAudio Processor Configuration Validation Report
**Generated**: 1757206350.4804516

## 📊 Summary
- **Total Configurations**: 1
- **Valid Configurations**: 1
- **Total Errors**: 0
- **Total Warnings**: 0
- **Placeholder Values**: 22

## 📄 config.example.yaml
**Status**: ✅ Valid
**Field Coverage**: 83.3%

### 🏷️ Placeholder Values
- `api_key`: `your-api-key-here`
- `api_key`: `your-api-key-here`
- `broadcaster_id`: `your-broadcaster-id`
- `llm.primary.ollama.host`: `http://localhost:11434`
- `llm.primary.openai.api_key`: `your-openai-key`
- `llm.primary.anthropic.api_key`: `your-anthropic-key`
- `llm.primary.xai.api_key`: `your-xai-key`
- `llm.primary.google.api_key`: `your-google-key`
- `llm.primary.groq.api_key`: `your-groq-key`
- `llm.fallback.ollama.host`: `http://localhost:11434`
- `llm.fallback.openai.api_key`: `your-fallback-openai-key`
- `llm.fallback.anthropic.api_key`: `your-anthropic-key`
- `llm.fallback.xai.api_key`: `your-xai-key`
- `llm.fallback.google.api_key`: `your-google-key`
- `llm.fallback.groq.api_key`: `your-groq-key`
- `llm.validator.ollama.host`: `http://localhost:11434`
- `llm.validator.openai.api_key`: `your-openai-key`
- `llm.validator.anthropic.api_key`: `your-anthropic-key`
- `llm.validator.google.api_key`: `your-google-key`
- `llm.validator.groq.api_key`: `your-groq-key`
- `embeddings.primary.openai.api_key`: `your-openai-key`
- `embeddings.primary.ollama.host`: `http://localhost:11434`

### 📋 Configuration Sections
- ✅ **api_key** (Required)
- ✅ **broadcaster_id** (Required)
- ✅ **llm** (Required)
  - ✅ primary (Required)
  - ✅ fallback
  - ✅ validator
- ✅ **metadata_processing**
  - ✅ description
  - ✅ hashtags
- ❌ **audio_processing**
- ✅ **debug**

## 💡 Recommendations
- Replace placeholder values with actual configuration
- Create config.yaml from config.example.yaml template
