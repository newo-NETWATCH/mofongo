# Worker (the photo tagger)

Runs on the EC2 instance. It polls the SQS photo queue, tags each photo with a zero-shot CLIP model and writes the tags to the Items table. The tag write is what starts the matcher. Design: `docs/decisions/0004-clip-on-ec2-with-sqs-pull.md`. Item fields: `docs/data-model.md` section 4.1.

## Files

| File | Job |
|---|---|
| `worker.py` | Main loop: long-poll, parse the S3 event, read the photo, tag, write, delete the message. Entry point. |
| `tagger.py` | Loads the model once, scores a photo, keeps the top 3. |
| `store.py` | The conditional DynamoDB updates. |
| `config.py` | Settings from environment variables. |
| `vocab.py` | The category and color word lists. |
| `check_vocab.py` | Checks `vocab.py` against `docs/data-model.md` and `backend/matcher/vocab.py`. |
| `deploy/mofongo-worker.service` | Reference copy of the systemd unit. The bootstrap in `infra/modules/tagger` writes the real one. |
| `requirements.txt` | Pinned packages (torch is installed separately, see below). |

## The model

open_clip `ViT-B-32` with the `laion2b_s34b_b79k` weights (MIT code, MIT weights). It loads once when the service starts. The text prompts are encoded once too, so each photo costs one image pass on the CPU.

For each photo it scores two lists separately (softmax over each list, using the model's own logit scale):

- Categories: `a photo of {CLIP phrase}` for the 13 values in data-model 2.1. `other` has no phrase, so CLIP never returns it.
- Colors: `a photo of a {CLIP word} object` for the 12 values in data-model 2.2.

It keeps the top 3 of each as `{value, score}`, with `score` a whole percent. The model card calls this a research model and asks for testing with a fixed class list first. Test the tags on sample photos before the first release (ADR 0004, M2). The prompts in `vocab.py` are the first thing to tune if tags are poor.

## What it writes

One conditional `UpdateItem` on `Items`, with the condition `status = LISTED AND tagStatus = PENDING AND photoKey = <the event's key>`:

| Outcome | Written |
|---|---|
| Tagged | `tagStatus = TAGGED`, `clipTags = {categories: [...3], colors: [...3]}`, `taggedAt`, and `tagError` removed |
| Photo cannot be read | `tagStatus = FAILED`, `tagError` (a short fixed sentence, never exception text) |

`PENDING` to `TAGGED` while `LISTED` is the change the matcher's stream filter waits for (data-model 6.2). The condition means:

- a `RETURNED` item is never touched,
- a duplicate S3 event cannot tag twice or turn a good item into `FAILED`,
- an event whose key is not the item's own `photoKey` is ignored.

Before reading the photo, the worker does one consistent `GetItem` and skips the CLIP run if the item is not LISTED and PENDING.

## Messages: delete or keep

| Case | Message |
|---|---|
| Tagged, or nothing to do (item gone, already tagged, returned, test event, other key or bucket) | deleted |
| Photo unreadable: not JPEG, PNG or WebP, corrupt, over `MAX_PHOTO_BYTES`, over `MAX_IMAGE_PIXELS`, or not in S3 | marked `FAILED`, then deleted |
| Transient error (S3, DynamoDB, SQS, the model) | kept. It returns after the visibility timeout, and after `maxReceiveCount` tries the redrive policy moves it to the dead-letter queue, which has an alarm |
| Body is not JSON | kept, so it reaches the dead-letter queue where someone sees it |

A photo marked `FAILED` stays `FAILED`. To retry one by hand after a fix, set its `tagStatus` back to `PENDING` and send the message again (or redrive it from the dead-letter queue).

On SIGTERM (service stop, instance stop) the worker finishes the photo it is on and exits. The visibility timeout must be longer than a batch of tagging runs. The worker stops taking new messages from a batch at 80% of it.

## Settings

Environment variables, written to `/etc/mofongo/worker.env` by the instance bootstrap. Full list and defaults in `config.py`.

| Variable | Needed | Notes |
|---|---|---|
| `QUEUE_URL` | yes | The main photo queue, not the dead-letter queue. `PHOTO_QUEUE_URL` also works. |
| `PHOTOS_BUCKET` | yes | Events for any other bucket are ignored. |
| `ITEMS_TABLE` | yes | |
| `REGION` / `AWS_REGION` | no | Default `us-east-2`. |
| `VISIBILITY_TIMEOUT` | no | Default 300. Keep it equal to the queue's setting. |

No credentials are set anywhere. boto3 uses the instance role through IMDSv2.

## IAM the instance role needs (least privilege)

- SQS on the photo queue: `ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`, `GetQueueAttributes`.
- S3: `GetObject` on `photos/*` of the photos bucket only.
- DynamoDB on the Items table only: `GetItem` and `UpdateItem`.
- `AmazonSSMManagedInstanceCore` for Session Manager.

## First boot and the model download

On the first boot the bootstrap installs the packages (CPU-only torch, about 200 MB, then open_clip, Pillow and boto3) and downloads the weights (about 600 MB) from Hugging Face into `HF_HOME` (`/opt/mofongo/hf`). This needs outbound internet, which the NAT gateway gives (ADR 0005 option A). Expect several minutes. The root volume keeps the cache, so a weekday stop and start does not download again, and the service runs with `HF_HUB_OFFLINE=1`.

Model load at service start takes a few seconds to a minute on 2 vCPUs. Until it finishes, nothing is polled and messages wait in the queue.

### Pinning the weights

Set `clip_model_sha256` in the tagger module to check the downloaded file in the bootstrap. To skip Hugging Face at run time altogether, put a checkpoint file on the instance and set `CLIP_WEIGHTS_PATH` to it.

## Word lists must stay in step

`vocab.py` holds the lists from data-model 2.1 and 2.2. Section 2.4 says to change the forms, the JSON Schemas, the tagger and the doc in one commit. This one also has to match `backend/matcher/vocab.py`. Check with:

```
python worker/check_vocab.py
```

Adding a value is safe. Never rename or remove a value that is already stored.

## Running it

On the instance it is a service: `sudo systemctl status mofongo-worker`, and `sudo tail -f /var/log/mofongo/worker.log` through Session Manager. There is no SSH.

Locally (not needed for the build, and it needs torch):

```
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 torchvision==0.20.1
pip install -r worker/requirements.txt
python -m py_compile worker/*.py
```

The worker has not been run against the model, AWS or a real photo yet. The speed per photo on `c7i-flex.large` is not measured.
