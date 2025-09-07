# SermonAudio Processor Configuration Validation Report
**Generated**: 1757204767.8262198

## 📊 Summary
- **Total Configurations**: 2
- **Valid Configurations**: 1
- **Total Errors**: 3
- **Total Warnings**: 0
- **Placeholder Values**: 39

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

## 📄 examples_config.yaml
**Status**: ❌ Invalid
**Field Coverage**: 0.0%

### ❌ Errors
- Missing required field: api_key
- Missing required field: broadcaster_id
- Missing required field: llm

### 🏷️ Placeholder Values
- `llm_xai_example.primary.openai.api_key`: `xai-your-api-key-here`
- `llm_xai_example.primary.openai.api_key`: `xai-your-api-key-here`
- `llm_xai_example.fallback.openai.api_key`: `sk-your-openai-key-here`
- `llm_xai_example.fallback.openai.api_key`: `sk-your-openai-key-here`
- `llm_anthropic_example.primary.openai.api_key`: `sk-ant-your-anthropic-key-here`
- `llm_anthropic_example.primary.openai.api_key`: `sk-ant-your-anthropic-key-here`
- `llm_anthropic_example.fallback.ollama.host`: `http://localhost:11434`
- `llm_groq_example.primary.openai.api_key`: `gsk-your-groq-key-here`
- `llm_groq_example.primary.openai.api_key`: `gsk-your-groq-key-here`
- `llm_groq_example.fallback.openai.api_key`: `xai-your-xai-key-here`
- `llm_groq_example.fallback.openai.api_key`: `xai-your-xai-key-here`
- `llm_local_example.primary.openai.base_url`: `http://localhost:8000/v1`
- `llm_local_example.fallback.ollama.host`: `http://localhost:11434`
- `llm_premium_budget.primary.openai.api_key`: `sk-your-openai-key-here`
- `llm_premium_budget.primary.openai.api_key`: `sk-your-openai-key-here`
- `llm_premium_budget.fallback.openai.api_key`: `sk-your-openai-key-here`
- `llm_premium_budget.fallback.openai.api_key`: `sk-your-openai-key-here`

### 📋 Configuration Sections
- ❌ **api_key** (Required)
- ❌ **broadcaster_id** (Required)
- ❌ **llm** (Required)
- ❌ **metadata_processing**
- ❌ **audio_processing**
- ❌ **debug**

## 💡 Recommendations
- Replace placeholder values with actual configuration
- Fix validation errors in: examples_config.yaml
- Create config.yaml from config.example.yaml template
