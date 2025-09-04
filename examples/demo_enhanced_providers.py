#!/usr/bin/env python3
"""
Demonstration script showing the enhanced LLM provider configuration.
This script shows how easy it is to switch between different LLM providers.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from llm_manager import LLMManager


def demo_provider_switching():
    """Demonstrate switching between different provider configurations."""
    
    print("🎯 Enhanced LLM Provider Configuration Demo")
    print("=" * 60)
    
    # Example configurations for each provider type
    provider_configs = {
        "OpenAI": {
            'llm': {
                'primary': {
                    'provider': 'openai',
                    'openai': {
                        'api_key': 'sk-demo-key',
                        'model': 'gpt-4o'
                    }
                }
            }
        },
        "Anthropic (Claude)": {
            'llm': {
                'primary': {
                    'provider': 'anthropic',
                    'anthropic': {
                        'api_key': 'sk-ant-demo-key'
                        # model will default to claude-3-5-sonnet-20241022
                    }
                }
            }
        },
        "xAI (Grok)": {
            'llm': {
                'primary': {
                    'provider': 'xai',
                    'xai': {
                        'api_key': 'xai-demo-key'
                        # model will default to grok-beta
                    }
                }
            }
        },
        "Google (Gemini)": {
            'llm': {
                'primary': {
                    'provider': 'google',
                    'google': {
                        'api_key': 'google-demo-key',
                        'model': 'gemini-1.5-pro'  # Override default
                    }
                }
            }
        },
        "Groq": {
            'llm': {
                'primary': {
                    'provider': 'groq',
                    'groq': {
                        'api_key': 'gsk-demo-key'
                        # model will default to llama-3.1-70b-versatile
                    }
                }
            }
        },
        "Ollama (Local)": {
            'llm': {
                'primary': {
                    'provider': 'ollama',
                    'ollama': {
                        'host': 'http://localhost:11434',
                        'model': 'llama3.1:8b'
                    }
                }
            }
        }
    }
    
    print("🚀 Initializing providers...")
    print()
    
    for provider_name, config in provider_configs.items():
        try:
            llm_manager = LLMManager(config)
            provider_info = llm_manager.get_provider_info()
            primary = provider_info.get('primary', {})
            
            print(f"✅ {provider_name}")
            print(f"   Provider Type: {primary.get('type', 'unknown')}")
            print(f"   Model: {primary.get('model', 'unknown')}")
            
            # Show base URL for OpenAI-compatible providers
            if hasattr(llm_manager.primary_provider, 'base_url'):
                base_url = llm_manager.primary_provider.base_url
                if base_url:
                    print(f"   Base URL: {base_url}")
            print()
            
        except Exception as e:
            print(f"❌ {provider_name}: {e}")
            print()


def demo_fallback_scenarios():
    """Demonstrate different fallback scenarios."""
    
    print("🔄 Fallback Scenarios Demo")
    print("=" * 40)
    
    fallback_scenarios = [
        {
            "name": "High-end → Budget",
            "description": "Claude Sonnet → Groq LLaMA (cost optimization)",
            "config": {
                'llm': {
                    'primary': {
                        'provider': 'anthropic',
                        'anthropic': {
                            'api_key': 'sk-ant-demo',
                            'model': 'claude-3-5-sonnet-20241022'
                        }
                    },
                    'fallback': {
                        'enabled': True,
                        'provider': 'groq',
                        'groq': {
                            'api_key': 'gsk-demo',
                            'model': 'llama-3.1-8b-instant'
                        }
                    }
                }
            }
        },
        {
            "name": "Cloud → Local",
            "description": "Grok → Local Ollama (privacy/latency)",
            "config": {
                'llm': {
                    'primary': {
                        'provider': 'xai',
                        'xai': {'api_key': 'xai-demo'}
                    },
                    'fallback': {
                        'enabled': True,
                        'provider': 'ollama',
                        'ollama': {
                            'host': 'http://localhost:11434',
                            'model': 'llama3.1:8b'
                        }
                    }
                }
            }
        },
        {
            "name": "Multi-Cloud",
            "description": "Google Gemini → OpenAI GPT (redundancy)",
            "config": {
                'llm': {
                    'primary': {
                        'provider': 'google',
                        'google': {'api_key': 'google-demo'}
                    },
                    'fallback': {
                        'enabled': True,
                        'provider': 'openai',
                        'openai': {'api_key': 'sk-demo'}
                    }
                }
            }
        }
    ]
    
    for scenario in fallback_scenarios:
        try:
            llm_manager = LLMManager(scenario['config'])
            provider_info = llm_manager.get_provider_info()
            
            primary = provider_info.get('primary', {})
            fallback = provider_info.get('fallback', {})
            
            print(f"✅ {scenario['name']}")
            print(f"   {scenario['description']}")
            print(f"   Primary: {primary.get('type')} ({primary.get('model')})")
            print(f"   Fallback: {fallback.get('type')} ({fallback.get('model')})")
            print()
            
        except Exception as e:
            print(f"❌ {scenario['name']}: {e}")
            print()


def demo_configuration_comparison():
    """Show the difference between old and new configuration styles."""
    
    print("📋 Configuration Style Comparison")
    print("=" * 50)
    
    print("🔴 OLD WAY (still supported for backward compatibility):")
    print("""
llm:
  primary:
    provider: "openai"
    openai:
      api_key: "xai-your-key"
      model: "grok-beta"
      base_url: "https://api.x.ai/v1"  # Had to remember this!
""")
    
    print("🟢 NEW WAY (cleaner and more intuitive):")
    print("""
llm:
  primary:
    provider: "xai"
    xai:
      api_key: "xai-your-key"
      # model defaults to grok-beta
      # base_url automatically set to https://api.x.ai/v1
""")
    
    print("✨ Benefits of the new approach:")
    print("   • Intuitive provider names (anthropic, xai, google, groq)")
    print("   • Smart defaults for models and endpoints")
    print("   • Cleaner configuration files")
    print("   • Better user experience")
    print("   • Backward compatibility maintained")


if __name__ == "__main__":
    demo_provider_switching()
    demo_fallback_scenarios()
    demo_configuration_comparison()
    
    print("🎉 Demo completed!")
    print()
    print("💡 To use these providers in your own configuration:")
    print("   1. Copy config.example.yaml to config.yaml")
    print("   2. Choose your preferred provider type")
    print("   3. Add your API key")
    print("   4. Optionally customize the model")
    print("   5. Set up fallback provider for reliability")