<h1>
  <a href="https://ubuntu.com/advantage" target="_blank">
    <img src="./.assets/circle_of_friends.png" width="33"/>
  </a>
  <br>
  Ubuntu Advantage Client
</h1>

###### Clean and Consistent CLI for your Ubuntu Advantage Systems

![Latest Version](https://img.shields.io/github/v/tag/canonical/ubuntu-advantage-client.svg?label=Latest%20Version)
![CI](https://github.com/canonical/ubuntu-advantage-client/actions/workflows/ci-base.yaml/badge.svg?branch=main)

The Ubuntu Advantage (UA) Client provides users with a simple mechanism to
view, enable, and disable offerings from Canonical on their system. The
following entitlements are supported:

- [Common Criteria EAL2 certification artifacts provisioning](https://ubuntu.com/cc-eal)
- [Canonical CIS Benchmark Audit Tool](https://ubuntu.com/cis-audit)
- [Ubuntu Extended Security Maintenance](https://ubuntu.com/esm)
- [Robot Operating System Extended Security Maintenance](https://ubuntu.com/robotics/ros-esm)
- [FIPS 140-2 Certified Modules](https://ubuntu.com/fips)
- [FIPS 140-2 Non-Certified Module Updates](https://ubuntu.com/fips)
- [Livepatch Service](https://www.ubuntu.com/livepatch)


## Obtaining the Client

The client comes pre-installed on all Ubuntu systems in the debian
`ubuntu-advantage-tools` package. "Ubuntu Pro" images on AWS, Azure and GCP
will also contain `ubuntu-advantage-pro` which automates machine attach
on boot for custom AWS, Azure and GCP images.

### Support Matrix for the client
Ubuntu Advantage services are only available on Ubuntu Long Term Support (LTS) releases.
On interim Ubuntu releases, `ua status` will report most of the services as 'n/a' and disallow enabling those services.

Below is a list of platforms and releases ubuntu-advantage-tools supports

| Ubuntu Release | Build Architectures | Support Level |
| -------- | -------- | -------- |
| Trusty | amd64, arm64, armhf, i386, powerpc, ppc64el | Last release 19.6  |
| Xenial | amd64, arm64, armhf, i386, powerpc, ppc64el, s390x | Active SRU of all features |
| Bionic | amd64, arm64, armhf, i386, ppc64el, s390x | Active SRU of all features |
| Focal | amd64, arm64, armhf, ppc64el, riscv64, s390x | Active SRU of all features |
| Groovy | amd64, arm64, armhf, ppc64el, riscv64, s390x | Last release 27.1 |
| Hirsute | amd64, arm64, armhf, ppc64el, riscv64, s390x | Last release 27.5 |
| Impish | amd64, arm64, armhf, ppc64el, riscv64, s390x | Active SRU of all features |

Note: ppc64el will not have support for APT JSON hook messaging due to insufficient golang packages

Ubuntu Pro images are available on the following cloud platforms on all Ubuntu LTS releases (Xenial, Bionic, Focal):
1. AWS: [Ubuntu PRO](https://ubuntu.com/aws/pro) and [Ubuntu PRO FIPS](https://ubuntu.com/aws/fips)
2. Azure: [Ubuntu PRO](https://ubuntu.com/azure/pro) and [Ubuntu PRO FIPS](https://ubuntu.com/azure/fips)
3. GCP: [Ubuntu PRO](https://ubuntu.com/gcp/pro)

Additionally, there are 3 PPAs with different release channels of the Ubuntu Advantage Client:

1. Stable: This contains stable builds only which have been verified for release into Ubuntu stable releases or Ubuntu PRO images.
    - add with `sudo add-apt-repository ppa:ua-client/stable`
2. Staging: This contains builds under validation for release to stable Ubuntu releases and images
    - add with `sudo add-apt-repository ppa:ua-client/staging`
3. Daily: This PPA is updated every day with the latest changes.
    - add with `sudo add-apt-repository ppa:ua-client/daily`

Users can manually run the `ua` command to learn more or view the manpage.

## Terminology
 The following vocabulary is used to describe different aspects of the work
Ubuntu Advantage Client performs:

| Term | Meaning |
| -------- | -------- |
| UA Client | The python command line client represented in this ubuntu-advantage-client repository. It is installed on each Ubuntu machine and is the entry-point to enable any Ubuntu Advantage commercial service on an Ubuntu machine. |
| Contract Server | The backend service exposing a REST API to which UA Client authenticates in order to obtain contract and commercial service information and manage which support services are active on a machine.|
| Entitlement/Service | An Ubuntu Advantage commercial support service such as FIPS, ESM, Livepatch, CIS-Audit to which a contract may be entitled |
| Affordance | Service-specific list of applicable architectures and Ubuntu series on which a service can run |
| Directives | Service-specific configuration values which are applied to a service when enabling that service |
| Obligations | Service-specific policies that must be instrumented for support of a service. Example: `enableByDefault: true` means that any attached machine **MUST** enable a service on attach |


### Using a proxy
The UA Client can be configured to use an http/https proxy as needed for network requests.
In addition, the UA Client will automatically set up proxies for all programs required for
enabling Ubuntu Advantage services. This includes APT, Snaps, and Livepatch.

The proxy can be set using the `ua config set` command. HTTP/HTTPS proxies are
set using `http_proxy` and `https_proxy`, respectively. APT proxies are defined
separately, using `apt_http_proxy` and `apt_https_proxy`. The proxy is identified
by a string formatted as:

`<protocol>://[<username>:<password>@]<fqdn>:<port>`

### Pro Upgrade Daemon
UA client sets up a daemon on supported platforms (currently GCP only) to
detect if an Ubuntu Pro license is purchased for the machine. If a Pro license
is detected, then the machine is automatically attached.

If you are uninterested in UA services, you can safely stop and disable the
daemon using systemctl:

```
sudo systemctl stop ubuntu-advantage.service
sudo systemctl disable ubuntu-advantage.service
```

## Remastering custom golden images based on Ubuntu PRO

Vendors who wish to provide custom images based on Ubuntu PRO images can
follow the procedure below:

* Launch the Ubuntu PRO golden image
* Customize your golden image as you see fit
* If `ua status` shows attached, remove the UA artifacts to allow clean
  auto-attach on subsequent cloned VM launches
```bash
sudo ua detach
sudo rm -rf /var/log/ubuntu-advantage.log  # to remove credentials and tokens from logs
```
* Remove `cloud-init` first boot artifacts so the cloned VM boot is seen as a first boot
```bash
sudo cloud-init clean --logs
sudo shutdown -h now
```
* Use your cloud platform to clone or snapshot this VM as a golden image


## Contributing to ubuntu-advantage-tools
See [CONTRIBUTING.md](CONTRIBUTING.md)
