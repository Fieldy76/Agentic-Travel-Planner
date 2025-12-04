# Third-Party API Licenses & Attribution

This application uses the following third-party APIs and services. We are grateful to these providers for making their services available.

## Weather Data: Open-Meteo

**Service:** [Open-Meteo API](https://open-meteo.com/)  
**License:** [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)

Weather data provided by **Open-Meteo** under CC BY 4.0 license. Open-Meteo is a free weather API that provides forecast data from various national weather services.

**Attribution Requirements:**
- Provide appropriate credit to Open-Meteo
- Include link to the license
- Indicate if modifications were made to the data

**Citation:**
```
Weather data provided by Open-Meteo (https://open-meteo.com/)
Licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/)
```

**What we use:**
- Daily temperature forecasts (max/min)
- Weather condition codes
- Forecast data for travel planning

---

## Flight Data: Amadeus for Developers

**Service:** [Amadeus for Developers](https://developers.amadeus.com/)  
**License:** Amadeus for Developers General Terms of Use

We use the Amadeus API for flight search and booking functionality. The Amadeus for Developers platform provides access to travel industry data for testing and development purposes.

**Attribution Requirements:**
- No general attribution requirements for the test API
- Production use requires specific commercial licensing

**What we use:**
- Flight search (origin, destination, dates)
- Flight offers with pricing
- OAuth 2.0 authentication

**Note:** This application uses the Amadeus **test environment** for demonstration purposes. For production deployment, a commercial license and production API credentials are required.

---

## LLM Providers

This application supports multiple LLM providers. Users must provide their own API keys:

- **OpenAI** - [Terms of Use](https://openai.com/policies/terms-of-use)
- **Anthropic (Claude)** - [Commercial Terms](https://www.anthropic.com/legal/commercial-terms)
- **Google (Gemini)** - [Terms of Service](https://ai.google.dev/gemini-api/terms)

---

## Disclaimer

This application is provided for educational and demonstration purposes. When using in production:

1. Ensure you comply with all API terms of service
2. Obtain appropriate commercial licenses where required
3. Review and comply with rate limits and usage policies
4. Implement proper error handling and fallbacks
5. Consider data privacy and user consent requirements

For the most current licensing information, please visit the respective service providers' websites.
