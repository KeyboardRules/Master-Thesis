<?php

namespace NITSAN\NsBackup\Domain\Model;

use TYPO3\CMS\Extbase\DomainObject\AbstractEntity;

/***
 *
 * This file is part of the "[NITSAN] Backup" Extension for TYPO3 CMS.
 *
 * For the full copyright and license information, please read the
 * LICENSE.txt file that was distributed with this source code.
 *
 *  (c) 2019
 *
 ***/

/**
 * Backupglobal
 */
class Backupglobal extends AbstractEntity
{
    /**
     * emails
     *
     * @var string
     */
    public string $emails = '';

    /**
     * emailFrom
     *
     * @var string
     */
    public string $emailFrom = '';


    /**
     * emailSubject
     *
     * @var string
     */
    public string $emailSubject = '';

    /**
     * emailNotificationOnError
     *
     * @var int|null
     */
    public ?int $emailNotificationOnError = 0;


    /**
     * compress
     *
     * @var string
     */
    public string $compress = '';

    /**
     * php
     *
     * @var string
     */
    public string $php = '';

    /**
     * root
     *
     * @var string
     */
    public string $root = '';

    /**
     * siteurl
     *
     * @var string
     */
    public string $siteurl = '';

    /**
     * cleanup
     *
     * @var string
     */
    public string $cleanup = '';

    /**
     * cleanupQuantity
     *
     * @var int
     */
    public int $cleanupQuantity = 0;

    /**
     * Returns the emailSubject
     *
     * @return string emailSubject
     */
    public function getEmailSubject(): string
    {
        return $this->emailSubject;
    }

    /**
     * Sets the emailSubject
     *
     * @param string $emailSubject
     * @return void
     */
    public function setEmailSubject(string $emailSubject): void
    {
        $this->emailSubject = $emailSubject;
    }

    /**
     * Returns the emails
     *
     * @return string emails
     */
    public function getEmails(): string
    {
        return $this->emails;
    }

    /**
     * Sets the emails
     *
     * @param string $emails
     * @return void
     */
    public function setEmails(string $emails): void
    {
        $this->emails = $emails;
    }

    /**
     * Returns the emailFrom
     *
     * @return string emailFrom
     */
    public function getEmailFrom(): string
    {
        return $this->emailFrom;
    }

    /**
     * Sets the emailFrom
     *
     * @param string $emailFrom
     * @return void
     */
    public function setEmailFrom(string $emailFrom): void
    {
        $this->emailFrom = $emailFrom;
    }

    /**
     * Returns the emailNotificationOnError
     *
     * @return int|null $emailNotificationOnError
     */
    public function getEmailNotificationOnError(): ?int
    {
        return $this->emailNotificationOnError;
    }

    /**
     * Sets the emailNotificationOnError
     *
     * @param int|null $emailNotificationOnError
     * @return void
     */
    public function setEmailNotificationOnError(?int $emailNotificationOnError)
    {
        $this->emailNotificationOnError = $emailNotificationOnError;
    }

    /**
     * Returns the compress
     *
     * @return string $compress
     */
    public function getCompress(): string
    {
        return $this->compress;
    }

    /**
     * Sets the compress
     *
     * @param string $compress
     * @return void
     */
    public function setCompress(string $compress): void
    {
        $this->compress = $compress;
    }

    /**
     * Returns the php
     *
     * @return string $php
     */
    public function getPhp(): string
    {
        return $this->php;
    }

    /**
     * Sets the php
     *
     * @param string $php
     * @return void
     */
    public function setPhp(string $php): void
    {
        $this->php = $php;
    }

    /**
     * Returns the root
     *
     * @return string $root
     */
    public function getRoot(): string
    {
        return $this->root;
    }

    /**
     * Sets the root
     *
     * @param string $root
     * @return void
     */
    public function setRoot(string $root): void
    {
        $this->root = $root;
    }

    /**
     * Returns the siteurl
     *
     * @return string $siteurl
     */
    public function getSiteurl(): string
    {
        return $this->siteurl;
    }

    /**
     * Sets the siteurl
     *
     * @param string $siteurl
     * @return void
     */
    public function setSiteurl(string $siteurl): void
    {
        $this->siteurl = $siteurl;
    }

    /**
     * Returns the cleanupQuantity
     *
     * @return int $cleanupQuantity
     */
    public function getCleanupQuantity(): int
    {
        return $this->cleanupQuantity;
    }

    /**
     * Sets the cleanupQuantity
     *
     * @param int $cleanupQuantity
     * @return void
     */
    public function setcleanupQuantity(int $cleanupQuantity): void
    {
        $this->cleanupQuantity = $cleanupQuantity;
    }

    /**
     * Returns the cleanup
     *
     * @return string $cleanup
     */
    public function getCleanup(): string
    {
        return $this->cleanup;
    }

    /**
     * Sets the cleanup
     *
     * @param string $cleanup
     * @return void
     */
    public function setCleanup(string $cleanup): void
    {
        $this->cleanup = $cleanup;
    }
}
