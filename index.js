const { chromium } = require('playwright');
const TelegramBot = require('node-telegram-bot-api');
const fs = require('fs');

const TOKEN = '8596594907:AAHUQjk-ik3LGV7kI-4XhCn-fw1T-FHo6wU';
const CHAT = '-1003179573402';
const URL = 'https://1xlite-7636770.bar/ru/live/baccarat';
const LAST_NUMBER_FILE = './last_number.txt';
const BUSY_TABLES_FILE = './busy_tables.txt';

const bot = new TelegramBot(TOKEN, { polling: false });

let lastMessageId = null;
let lastMessageText = '';
let lastGameNumber = '0';

if (fs.existsSync(LAST_NUMBER_FILE)) {
    lastGameNumber = fs.readFileSync(LAST_NUMBER_FILE, 'utf8');
    console.log('Загружен последний номер:', lastGameNumber);
}

function getBusyTables() {
    try {
        if (fs.existsSync(BUSY_TABLES_FILE)) {
            const content = fs.readFileSync(BUSY_TABLES_FILE, 'utf8');
            return new Set(content.split('\n').filter(line => line.trim()));
        }
    } catch (e) {}
    return new Set();
}

function markTableBusy(tableId, browserId) {
    try {
        const busy = getBusyTables();
        busy.add(tableId);
        fs.writeFileSync(BUSY_TABLES_FILE, Array.from(busy).join('\n'));
        console.log(`🔒 Стол ${tableId} занят браузером ${browserId}`);
    } catch (e) {}
}

function markTableFree(tableId) {
    try {
        const busy = getBusyTables();
        busy.delete(tableId);
        fs.writeFileSync(BUSY_TABLES_FILE, Array.from(busy).join('\n'));
        console.log(`🔓 Стол ${tableId} освобожден`);
    } catch (e) {}
}

function formatCards(cards) {
    return cards.join('');
}

function determineTurn(playerCards, bankerCards) {
    if (playerCards.length === 2 && bankerCards.length === 2) return 'player';
    if (playerCards.length === 3 && bankerCards.length === 2) return 'banker';
    if (playerCards.length === 2 && bankerCards.length === 3) return 'player';
    return null;
}

function getGameNumberByTime() {
    const now = new Date();
    const mskTime = new Date(now.toLocaleString('en-US', { timeZone: 'Europe/Moscow' }));
    
    const currentHours = mskTime.getHours();
    const currentMinutes = mskTime.getMinutes();
    const currentSeconds = mskTime.getSeconds();
    
    const startHour = 3;
    const startMinute = 0;
    
    if (currentHours < startHour || (currentHours === startHour && currentMinutes < startMinute)) {
        return null;
    }
    
    let minutesSinceStart = (currentHours - startHour) * 60 + (currentMinutes - startMinute);
    
    if (currentSeconds < 5) {
        minutesSinceStart -= 1;
    }
    
    return minutesSinceStart + 1;
}

async function sendOrEditTelegram(newMessage) {
    if (!newMessage || newMessage === lastMessageText) return;
    
    try {
        if (lastMessageId) {
            await bot.editMessageText(newMessage, {
                chat_id: CHAT,
                message_id: lastMessageId
            });
        } else {
            const msg = await bot.sendMessage(CHAT, newMessage);
            lastMessageId = msg.message_id;
        }
        lastMessageText = newMessage;
        console.log('✅ Сообщение отправлено');
    } catch (e) {
        console.log('❌ TG error:', e.message);
        try {
            const msg = await bot.sendMessage(CHAT, newMessage);
            lastMessageId = msg.message_id;
            lastMessageText = newMessage;
        } catch (sendError) {}
    }
}

async function getTimerValue(game) {
    try {
        const timerText = await game.$eval('.dashboard-game-info__time', el => el.textContent.trim());
        const match = timerText.match(/(\d+):(\d+)/);
        if (match) {
            const minutes = parseInt(match[1]);
            const seconds = parseInt(match[2]);
            return minutes * 60 + seconds;
        }
    } catch (e) {}
    return 9999;
}

async function findFreeGameWithSmallestTimer(page, browserId) {
    console.log(`🔍 Браузер ${browserId} ищет свободный стол...`);
    
    const games = await page.$$('.dashboard-game');
    console.log(`Найдено столов: ${games.length}`);
    
    const busyTables = getBusyTables();
    console.log(`Занятые столы: ${Array.from(busyTables).join(', ') || 'нет'}`);
    
    let availableGames = [];
    
    for (let i = 0; i < games.length; i++) {
        const game = games[i];
        
        const hasTimer = await game.$('.dashboard-game-info__time') !== null;
        if (!hasTimer) continue;

        const isFinished = await game.evaluate(el => {
            const period = el.querySelector('.dashboard-game-info__period');
            return period?.textContent.includes('Игра завершена') ?? false;
        });

        if (!isFinished) {
            const link = await game.$('a[href*="/ru/live/baccarat/"]');
            if (link) {
                const href = await link.getAttribute('href');
                const tableId = href.split('/').pop();
                const timerSeconds = await getTimerValue(game);
                
                if (!busyTables.has(tableId)) {
                    availableGames.push({
                        index: i,
                        href,
                        tableId,
                        timer: timerSeconds
                    });
                    console.log(`📊 Стол ${i+1} (ID: ${tableId}): таймер ${timerSeconds} сек - СВОБОДЕН`);
                } else {
                    console.log(`⛔ Стол ${i+1} (ID: ${tableId}): ЗАНЯТ`);
                }
            }
        }
    }
    
    availableGames.sort((a, b) => a.timer - b.timer);
    
    if (availableGames.length > 0) {
        const selected = availableGames[0];
        console.log(`🎯 Браузер ${browserId} выбрал стол ${selected.index+1} (ID: ${selected.tableId}) с таймером ${selected.timer} сек`);
        markTableBusy(selected.tableId, browserId);
        return selected;
    }
    
    console.log('❌ Свободных столов не найдено');
    return null;
}

async function getCards(page) {
    if (page.isClosed()) return { player: [], banker: [], pScore: '0', bScore: '0' };
    
    const playerBlock = await page.$('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__cards').catch(() => null);
    const player = playerBlock ? await playerBlock.$$eval('li.baccarat-player__card-box', cards => {
        return cards.map(c => {
            const rankEl = c.querySelector('.baccarat-card__rank');
            if (!rankEl) return null;
            const rank = rankEl.textContent.trim();
            const suitIcon = c.querySelector('.baccarat-card__suit');
            let suit = '';
            if (suitIcon) {
                if (suitIcon.className.includes('spades')) suit = '♠️';
                else if (suitIcon.className.includes('hearts')) suit = '♥️';
                else if (suitIcon.className.includes('clubs')) suit = '♣️';
                else if (suitIcon.className.includes('diamonds')) suit = '♦️';
            }
            return rank + suit;
        }).filter(c => c !== null).slice(0, 3);
    }).catch(() => []) : [];

    const bankerBlock = await page.$('.baccarat-player--is-reversed .baccarat-player__cards').catch(() => null);
    const banker = bankerBlock ? await bankerBlock.$$eval('li.baccarat-player__card-box', cards => {
        return cards.map(c => {
            const rankEl = c.querySelector('.baccarat-card__rank');
            if (!rankEl) return null;
            const rank = rankEl.textContent.trim();
            const suitIcon = c.querySelector('.baccarat-card__suit');
            let suit = '';
            if (suitIcon) {
                if (suitIcon.className.includes('spades')) suit = '♠️';
                else if (suitIcon.className.includes('hearts')) suit = '♥️';
                else if (suitIcon.className.includes('clubs')) suit = '♣️';
                else if (suitIcon.className.includes('diamonds')) suit = '♦️';
            }
            return rank + suit;
        }).filter(c => c !== null).slice(0, 3);
    }).catch(() => []) : [];

    const pScore = await page.$eval('.baccarat-player:not(.baccarat-player--is-reversed) .baccarat-player__number', el => el.textContent).catch(() => '0');
    const bScore = await page.$eval('.baccarat-player--is-reversed .baccarat-player__number', el => el.textContent).catch(() => '0');

    return { player, banker, pScore, bScore };
}

async function monitorGame(page, gameNumber, tableId) {
    console.log(`🎮 Мониторинг игры #${gameNumber} (стол ${tableId})`);
    
    let lastCards = { player: [], banker: [], pScore: '0', bScore: '0' };
    
    while (true) {
        if (page.isClosed()) {
            console.log('⚠️ Страница закрыта, выход из мониторинга');
            break;
        }
        
        const cards = await getCards(page);
        
        const isGameOver = await page.evaluate(() => {
            const panel = document.querySelector('.market-grid__game-over-panel');
            return panel !== null;
        }).catch(() => false);
        
        if (isGameOver) {
            console.log('🏁 Игра завершена, проверяю карты...');
            
            let finalCards = cards;
            let retryCount = 0;
            
            while ((finalCards.player.length === 0 || finalCards.banker.length === 0) && retryCount < 5 && !page.isClosed()) {
                console.log(`⏳ Повторная попытка чтения карт (${retryCount + 1}/5)...`);
                await page.waitForTimeout(500).catch(() => {});
                finalCards = await getCards(page);
                retryCount++;
            }
            
            if (finalCards.player.length > 0 || finalCards.banker.length > 0) {
                cards.player = finalCards.player;
                cards.banker = finalCards.banker;
                cards.pScore = finalCards.pScore;
                cards.bScore = finalCards.bScore;
            }
            
            if (cards.player.length > 0 || cards.banker.length > 0 || cards.pScore !== '0' || cards.bScore !== '0') {
                const total = parseInt(cards.pScore) + parseInt(cards.bScore);
                const winner = cards.pScore > cards.bScore ? 'П1' : (cards.bScore > cards.pScore ? 'П2' : 'X');
                const noDrawFlag = cards.player.length === 2 && cards.banker.length === 2 ? '#R ' : '';
                
                let message;
                if (cards.pScore > cards.bScore) {
                    message = `#N${gameNumber} ✅${cards.pScore} (${formatCards(cards.player)}) - ${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
                } else if (cards.bScore > cards.pScore) {
                    message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) - ✅${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
                } else {
                    message = `#N${gameNumber} ${cards.pScore} (${formatCards(cards.player)}) 🔰 ${cards.bScore} (${formatCards(cards.banker)}) ${noDrawFlag}#${winner} #T${total}`;
                }
                
                await sendOrEditTelegram(message);
            }
            
            await page.waitForTimeout(10000).catch(() => {});
            break;
        }
        
        if (cards.player.length > 0 && cards.banker.length > 0) {
            const turn = determineTurn(cards.player, cards.banker);
            
            let message;
            if (turn === 'player') {
                message = `⏱№${gameNumber} 👉${cards.pScore}(${formatCards(cards.player)}) -${cards.bScore} (${formatCards(cards.banker)})`;
            } else if (turn === 'banker') {
                message = `⏱№${gameNumber} ${cards.pScore}(${formatCards(cards.player)}) -👉${cards.bScore} (${formatCards(cards.banker)})`;
            } else {
                message = `⏱№${gameNumber} ${cards.pScore}(${formatCards(cards.player)}) -${cards.bScore} (${formatCards(cards.banker)})`;
            }
            
            const cardsChanged = 
                JSON.stringify(cards.player) !== JSON.stringify(lastCards.player) ||
                JSON.stringify(cards.banker) !== JSON.stringify(lastCards.banker) ||
                cards.pScore !== lastCards.pScore ||
                cards.bScore !== lastCards.bScore;
            
            if (cardsChanged) {
                await sendOrEditTelegram(message);
                lastCards = { ...cards };
            }
        }
        
        await page.waitForTimeout(2000).catch(() => {});
    }
}

async function run() {
    const browserId = Math.floor(Math.random() * 1000);
    let browser;
    let timeout;
    let currentTableId = null;
    const startTime = Date.now();
    
    try {
        console.log(`\n🟢 Браузер ${browserId} открыт в ${new Date().toLocaleTimeString()}.${new Date().getMilliseconds()}`);
        
        // Исправленный launch с дополнительными флагами
        browser = await chromium.launch({ 
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--disable-software-rasterizer',
                '--disable-features=VizDisplayCompositor',
                '--single-process'
            ]
        });
        
        const page = await browser.newPage();
        
        timeout = setTimeout(async () => {
            console.log(`⏱ Браузер ${browserId} завершает работу (4 минуты)`);
            if (currentTableId) {
                markTableFree(currentTableId);
            }
            if (browser && browser.isConnected()) {
                await browser.close().catch(() => {});
            }
        }, 240000);
        
        try {
            await page.goto(URL, { timeout: 30000, waitUntil: 'domcontentloaded' });
        } catch (e) {
            console.log(`❌ Ошибка загрузки страницы:`, e.message);
            return;
        }
        
        const tableInfo = await findFreeGameWithSmallestTimer(page, browserId);
        if (!tableInfo) {
            console.log(`❌ Браузер ${browserId} не нашел свободных столов`);
            return;
        }
        
        currentTableId = tableInfo.tableId;
        console.log(`Браузер ${browserId} заходит в стол:`, tableInfo.href);
        
        try {
            await page.click(`a[href="${tableInfo.href}"]`);
        } catch (e) {
            console.log(`❌ Ошибка клика:`, e.message);
            return;
        }
        
        let gameNumber = getGameNumberByTime();
        if (!gameNumber) {
            console.log('⏰ До начала игр еще время');
            return;
        }
        
        gameNumber = gameNumber.toString();
        console.log('🎰 Номер игры:', gameNumber);
        
        lastGameNumber = gameNumber;
        fs.writeFileSync(LAST_NUMBER_FILE, gameNumber);
        
        let cardsAttempts = 0;
        let cards = { player: [], banker: [], pScore: '0', bScore: '0' };
        
        while (cardsAttempts < 12 && (cards.player.length === 0 || cards.banker.length === 0) && !page.isClosed()) {
            await page.waitForTimeout(5000).catch(() => {});
            cards = await getCards(page);
            cardsAttempts++;
            console.log(`⏳ Ожидание карт... попытка ${cardsAttempts}/12 (игрок: ${cards.player.length}, дилер: ${cards.banker.length})`);
        }
        
        if (cards.player.length > 0 && cards.banker.length > 0 && !page.isClosed()) {
            await monitorGame(page, gameNumber, currentTableId);
        } else {
            console.log('⚠️ Карты не появились за 12 попыток');
        }
        
    } catch (e) {
        console.log(`❌ Ошибка браузера ${browserId}:`, e.message);
    } finally {
        if (timeout) clearTimeout(timeout);
        if (currentTableId) {
            markTableFree(currentTableId);
        }
        if (browser && browser.isConnected()) {
            await browser.close().catch(() => {});
            console.log(`🔴 Браузер ${browserId} закрыт, проработал ${((Date.now() - startTime)/1000).toFixed(3)} секунды`);
        }
        lastMessageId = null;
        lastMessageText = '';
    }
}

function getDelayTo58() {
    const now = new Date();
    const seconds = now.getSeconds();
    const milliseconds = now.getMilliseconds();
    const targetSeconds = 58;
    
    let delaySeconds;
    if (seconds < targetSeconds) {
        delaySeconds = targetSeconds - seconds;
    } else {
        delaySeconds = (60 - seconds) + targetSeconds;
    }
    
    return (delaySeconds * 1000) - milliseconds;
}

(async () => {
    console.log('🤖 Бот Baccarat запущен');
    console.log('🎯 Беру СВОБОДНЫЙ стол с НАИМЕНЬШИМ таймером');
    console.log('⏱ Запуск в :58 каждой минуты');
    console.log('⏱ Жизнь браузера: 4 минуты');
    
    const initialDelay = getDelayTo58();
    const nextRunTime = new Date(Date.now() + initialDelay);
    console.log(`⏱ Первый запуск через ${(initialDelay/1000).toFixed(3)} секунд`);
    console.log(`⏱ Время первого запуска: ${nextRunTime.toLocaleTimeString()}.${nextRunTime.getMilliseconds()}`);
    
    await new Promise(resolve => setTimeout(resolve, initialDelay));
    console.log('✅ Синхронизировались!');
    
    while (true) {
        const now = new Date();
        console.log(`\n🚀 Запуск браузера в ${now.toLocaleTimeString()}.${now.getMilliseconds()}`);
        
        run();
        
        await new Promise(resolve => setTimeout(resolve, 60000));
    }
})();