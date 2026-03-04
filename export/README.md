# BVCS: Blender Version Control System

A seamless version control integration for Blender, allowing teams to sync objects and projects via S3 and a dedicated database.

---

## Installation

### 1. Download the Add-on
Download the latest `blender_vcs.zip` from the **Releases** section of this repository. 
> **Note:** Do not unzip the file manually. Blender installs the ZIP directly.

### 2. Install in Blender
1. Open Blender and go to **Edit → Preferences** (`Ctrl + ,`).
2. Navigate to the **Add-ons** tab.
3. Click the **down arrow** (top-right) and select **Install from Disk**.
4. Find your downloaded `blender_vcs.zip` and click **Install Add-on**.
<img width="1708" height="1176" alt="Screenshot from 2026-03-04 15-14-51" src="https://github.com/user-attachments/assets/29801173-9b8d-452d-b3a2-56218b5925d5" />


### 3. Enable & Access
1. Check the box next to **BVCS** to enable it.
2. In the 3D Viewport, press **N** to open the right-hand sidebar.
3. Click the **BVCS** tab to open the menu.
<img width="3092" height="1992" alt="Screenshot from 2026-03-04 15-15-40" src="https://github.com/user-attachments/assets/472add60-07f6-43c9-a4d5-b2bbc89a9b55" />

---

## Tutorial: How to Use BVCS

### 1. Authentication & Project Setup
Before syncing, you must log in to the system:
* **Log In / Sign Up:** Use the BVCS panel to enter your credentials.
* **Project Management:** Once logged in, you can **Open** an existing project or **Create New Project**.

<img width="3168" height="2002" alt="Screenshot from 2026-03-04 15-17-13" src="https://github.com/user-attachments/assets/b47dc715-6de0-4cab-a8cd-95b09aa2fe2a" />

### 2. Syncing Your Work (Commit & Push)
BVCS follows a "Stage → Commit → Push" workflow. Follow these steps to ensure your objects are saved to the cloud:

1.  **Select Objects:** In the 3D Viewport, select the specific objects you want to version.
2.  **Save File:** Save your current Blender file (`Ctrl + S`).
3.  **Stage:** With your objects still selected, click the **Stage** button.
4.  **Commit:** Click **Commit**. A popup will appear—type in your commit message (e.g., "Updated character topology").
5.  **Push:** Click **Push to S3 and Database**. 

Your objects are now uploaded! You can now view or download them directly from the web interface.

### 3. Collaborating & History
* **Pulling Changes:** If a teammate has made changes or you are missing updates, click the **Pull** button to sync the latest version to your local file.
* **Viewing History:** Use the **Project Files Selector** dropdown to browse and view previous commits. This is useful for tracking progress or checking older iterations of your work.

---

## Quick Tips
* **Selection is Key:** Only the objects selected when you hit **Stage** will be included in your commit.
* **Web Access:** Every push is instantly mirrored to the web project, allowing for easy downloads outside of Blender.
