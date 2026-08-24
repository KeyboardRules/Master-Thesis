<?php

namespace NITSAN\NsBackup\Controller;

use Doctrine\DBAL\Exception;
use Symfony\Component\Mime\Address;
use TYPO3\CMS\Core\Core\Environment;
use TYPO3\CMS\Core\Mail\MailMessage;
use TYPO3\CMS\Core\Page\PageRenderer;
use Psr\Http\Message\ResponseInterface;
use TYPO3\CMS\Core\Utility\GeneralUtility;
use Psr\Http\Message\ServerRequestInterface;
use TYPO3\CMS\Backend\Template\ModuleTemplate;
use TYPO3\CMS\Core\Type\ContextualFeedbackSeverity;
use TYPO3\CMS\Backend\Template\ModuleTemplateFactory;
use TYPO3\CMS\Extbase\Mvc\Controller\ActionController;
use NITSAN\NsBackup\Domain\Repository\BackupglobalRepository;
use TYPO3\CMS\Extbase\Utility\LocalizationUtility as transalte;

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
 * BackupsController
 */
class BackupsController extends ActionController
{
    /**
     * errorValidation
     */
    protected string $errorValidation;

    /**
     * @param ModuleTemplateFactory $moduleTemplateFactory
     * @param BackupglobalRepository $backupglobalRepository
     * @param BackupBaseController $backupBaseController
     */
    public function __construct(
        protected ModuleTemplateFactory $moduleTemplateFactory,
        protected BackupglobalRepository $backupglobalRepository,
        protected BackupBaseController $backupBaseController
    ) {

    }

    /**
     * Initializes the view before invoking an action method.
     * Override this method to solve assign variables common for all actions
     * or prepare the view in another way before the action is called.
     *
     */
    public function initializeView(): void
    {
        // Global error check
        $this->errorValidation = $this->backupBaseController->globalErrorValidation();
        if(!empty($this->errorValidation)) {
            $header = transalte::translate('global.errorvalidation', 'ns_backup');
            $message = transalte::translate('global.errorvalidation.message', 'ns_backup');
            $this->addFlashMessage($message, $header, ContextualFeedbackSeverity::ERROR);
        }
    }

    /**
     * action dashboard
     * @return ResponseInterface
     * @throws Exception
     */
    public function dashboardAction(): ResponseInterface
    {
        $pageRenderer = GeneralUtility::makeInstance(className: PageRenderer::class);
        $pageRenderer->loadJavaScriptModule('@nitsan/ns-backup/jquery.js');
        $pageRenderer->loadJavaScriptModule('@nitsan/ns-backup/Main.js');

        $globalSettingsData = $this->backupglobalRepository->findAll();
        $arrBackupData = $this->backupglobalRepository->findBackupDataAll(5);

        $arrMultipleVars = [
            'cleanup' => constant('cleanup'),
            'backuptype' => constant('backuptype'),
            'compress' => constant('compress'),
            'backupglobal' => $globalSettingsData[0],
            'action' => 'dashboard',
            'arrBackupData' => $arrBackupData,
            'errorValidation' => $this->errorValidation,
            'modalAttr' => 'data-bs-'
        ];
        $view = $this->initializeModuleTemplate($this->request);
        $view->assignMultiple($arrMultipleVars);
        return $view->renderResponse('Backups/Dashboard');
    }

    /**
     * action backuprestore
     * @return ResponseInterface
     * @throws Exception
     */
    public function backuprestoreAction(): ResponseInterface
    {
        $pageRenderer = GeneralUtility::makeInstance(PageRenderer::class);
        $pageRenderer->loadJavaScriptModule('@nitsan/ns-backup/jquery.js');
        $pageRenderer->loadJavaScriptModule('@nitsan/ns-backup/Main.js');

        $globalSettingsData = $this->backupglobalRepository->findAll();
        $arrMultipleVars = [
            'cleanup' => constant('cleanup'),
            'backuptype' => constant('backuptype'),
            'compress' => constant('compress'),
            'backupglobal' => $globalSettingsData[0],
            'action' => 'backuprestore',
            'errorValidation' => $this->errorValidation
        ];

        $arrPost = $this->request->getArguments();
        // "RUN" Backup from "Manual Backup Module"
        $arrPost = $arrPost['backuprestore'] ?? '';

        if(!empty($arrPost['backupFolderSettings']) && empty($this->errorValidation)) {

            // Create json and take backup
            $arrResponse = $this->backupBaseController->generateBackup($arrPost);

            if($arrResponse['log'] == 'error') {
                // Error Flash-Message
                $mesHeader = transalte::translate('manualbackup.error', 'ns_backup');
                $backup_file = $arrResponse['backup_file'];
                $this->addFlashMessage($backup_file, $mesHeader, ContextualFeedbackSeverity::ERROR);
            } else {
                // Success Flash-Message
                $mesHeader = transalte::translate('manualbackup.success', 'ns_backup');
                $backup_file = transalte::translate('backup.downloaded', 'ns_backup').' '.$arrResponse['backup_file'];
                $this->addFlashMessage($backup_file, $mesHeader);
                
                $response = (array) json_decode($arrResponse['log']);
                if (isset($response['errorCount']) && $response['errorCount'] > 0) {
                    $globalSettingsData = $this->backupglobalRepository->findAll();
                    if ($globalSettingsData[0]->emailNotificationOnError){
                        $mail = GeneralUtility::makeInstance(MailMessage::class);
                        $emails = explode(',',$globalSettingsData[0]->emails);
                        foreach ($emails as $email) {
                            $mail->from(new Address($globalSettingsData[0]->emailFrom, 'Backup'));
                            $mail->to(
                                new Address($email)
                            );
                            $mail->subject($globalSettingsData[0]->emailSubject);
                            $mail->html('<p><strong>Backup Error:</strong> \''.$response['errors'][0]->message.'\'</p>');
                            $mail->send();
                        }
                        $this->addFlashMessage($response['errors'][0]->message, transalte::translate('manualbackup.warning', 'ns_backup'), ContextualFeedbackSeverity::WARNING);
                    }
                }

                // Pass to Fluid
                $arrMultipleVars['isManualBackup'] = '1';
                $arrMultipleVars['log'] = '<pre class="pre-scrollable"><code class="json">'. json_encode(json_decode($arrResponse['log']), JSON_PRETTY_PRINT) .'</code></pre>';
                $arrMultipleVars['download_url'] = $arrResponse['download_url'];
            }
        }

        // List Backup History
        $objBackupData = $this->backupglobalRepository->findBackupDataAll();
        foreach ($objBackupData as $keyBackup => $valueBackup) {
            // Formate Log
            if ($valueBackup['logs']) {
                $objBackupData[$keyBackup]['logs'] = '<pre class="pre-scrollable"><code class="json">' . json_encode(json_decode($objBackupData[$keyBackup]['logs']), JSON_PRETTY_PRINT) . '</code></pre>';
            }
            if($valueBackup['download_url']) {
                $file_headers = @get_headers($valueBackup['download_url']);
                $objBackupData[$keyBackup]['isDownload'] = (!$file_headers || $file_headers[0] == 'HTTP/1.1 404 Not Found') ? false : true;
            }

        }
        $arrMultipleVars['arrBackupData'] = $objBackupData;
        $arrMultipleVars['modalAttr'] = 'data-bs-';
        $view = $this->initializeModuleTemplate($this->request);
        $view->assignMultiple($arrMultipleVars);
        return $view->renderResponse('Backups/Backuprestore');
    }

    /**
     * action deletebackupbackup
     * @return ResponseInterface
     * @throws Exception
     */
    public function deletebackupbackupAction(): ResponseInterface
    {
        $request = $this->request->getQueryParams();
        $uid = $request['uid'];

        $arrBackup = $this->backupglobalRepository->findBackupByUid($uid);
        // Let's delete it
        $this->backupglobalRepository->removeBackupData($uid);

        // Remove file from Physical location
        if(file_exists($arrBackup['filenames'])) {
            unlink($arrBackup['filenames']);
        }

        $rootPath = $this->globalSettingsData[0]->root ?? (Environment::getProjectPath() ?? '');
        if(Environment::isComposerMode()) {
            $rootPath = Environment::getPublicPath();
        }
        $jsonFolder = $rootPath.'/uploads/tx_nsbackup/json/';
        if(file_exists($jsonFolder.$arrBackup['jsonfile'])) {
            unlink($jsonFolder.$arrBackup['jsonfile']);
        }

        $jsonLogFile = str_replace("_configuration", "_log", $arrBackup['jsonfile']);
        if(file_exists($jsonFolder.$jsonLogFile)) {
            unlink($jsonFolder.$jsonLogFile);
        }

        $headerMsg = transalte::translate('delete.backup.data', 'ns_backup');
        $msg = transalte::translate('delete.backup.message', 'ns_backup').$arrBackup['filenames'];
        $this->addFlashMessage($msg, $headerMsg, ContextualFeedbackSeverity::OK, true);
        die;
    }

    /**
     * Initialize Module Template
     */
    protected function initializeModuleTemplate(
        ServerRequestInterface $request
    ): ModuleTemplate {
        return $this->moduleTemplateFactory->create($request);
    }
}
