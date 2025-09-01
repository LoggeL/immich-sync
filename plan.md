Implement the project (immich-sync) based on the sync service py

This project allows users to sync their photos between multiple immich instances.
Each user registers with a username and password, but has to provide the url and api key of their immich instance.
Each user can create a sync (group) and add other users to it.
Each user in the sync has to select an album id from their immich instance which will be synced to the other users in the sync.
The sync service will run in a separate thread and will sync the photos between the users in the sync.
The UI will regularly poll the sync service for progress and a detailed status.
The sync will trigger daily at 00:00 UTC or when the user triggers it manually.
Each sync has a expiration date after which the automatic sync will stop.
Create a frontend and backend.
