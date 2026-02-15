# 📘 Cloudflare Statistics – Home Assistant Integration

This custom integration adds **Cloudflare Analytics** data to Home Assistant as native sensors.  
It uses the official Cloudflare Analytics API and requires **no YAML configuration**.

All sensors are created automatically after setup and include:

- Pageviews  
- Unique visitors  
- Bandwidth usage  
- And more  

---

## 🚀 Features

- Full **UI configuration** (Config Flow)  
- **HACS compatible**  
- Automatically creates all available Cloudflare Analytics sensors  
- Uses Cloudflare’s official API  
- No WordPress plugins or external services required  
- Polling interval configurable  

---

# 📦 Installation via HACS

### 1. Add the repository

1. Open Home Assistant  
2. Go to **HACS → Integrations → Custom repositories**  
3. Add repository URL:  
   ```
   https://github.com/simonsays187/cloudflare-statistics
   ```
4. Category: **Integration**  
5. Click **Add**

### 2. Install the integration

1. In HACS, search for **Cloudflare Statistics**  
2. Install it  
3. Restart Home Assistant

---

# 🧩 Adding the Integration in Home Assistant

After restarting:

1. Go to **Settings → Devices & Services**  
2. Click **Add Integration**  
3. Search for **Cloudflare Statistics**  
4. Enter:
   - **Zone ID**
   - **API Token**
   - **Update interval (optional)**  
5. Confirm

Home Assistant will automatically create all available Cloudflare sensors.

---

# 🔑 How to Find Your Cloudflare Zone ID

1. Log in to the Cloudflare Dashboard  
2. Select your domain (e.g., *example.com*)  
3. On the **Overview** page, look on the right side  
4. You will see:

**Zone ID**

Example:

```
a1b2c3d4e5f6g7h8i9j0
```

Copy this value into the integration setup.

---

# 🔐 How to Generate the Correct Cloudflare API Token

The integration requires a **restricted API token** with read‑only access to Analytics.

### Steps:

1. Log in to Cloudflare  
2. Click your profile icon (top right)  
3. Select **My Profile**  
4. Go to **API Tokens**  
5. Click **Create Token**  
6. Choose template: **Read Analytics**  
   If not available, choose **Custom Token**

### Required permissions:

| Scope | Permission |
|-------|------------|
| **Zone** | **Analytics → Read** |

### Zone restrictions:

- Select **only the domain** you want Home Assistant to access

### Create the token

You will receive a token like:

```
cf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Copy this token into the integration setup in Home Assistant.

---

# 📊 Available Sensors

The integration automatically creates sensors for all values available:

This includes:

### Requests
- `views_today`
- `views_week`
- `views_month`

### Unique Visitors
- `uniques_today`
- `uniques_week`
- `uniques_month`

### Bandwidth
- `bandwidth_today`
- `bandwidth_week`
- `bandwidth_month`

### Countries (only for non free Plan)
- `country_today`
- `country_week`
- `country_month`

### Web Analytics (only for non free Plan)
- `page_load_today`
- `page_load_week`
- `page_load_month`
- `visits_today`
- `visits_week`
- `visits_month`
- `page_views_today`
- `page_views_week`
- `page_views_month`

---

# 🛠 Troubleshooting

### No sensors appear

- Make sure the integration is installed via HACS  
- Restart Home Assistant after installation  
- Check **Settings → System → Logs** for entries containing:  
  ```
  cloudflare_statistics
  ```
- Verify:
  - Zone ID is correct  
  - API token has the correct permissions  
  - Domain name in `manifest.json` matches the folder name  
  - Integration folder is located at:  
    ```
    config/custom_components/cloudflare-statistics/
    ```


Brought to you by HumanEngine: https://humanengine.net