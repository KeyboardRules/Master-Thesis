<?php

declare(strict_types=1);

namespace MoonShine\Laravel\Fields\Relationships;

use Closure;
use Illuminate\Database\Eloquent\Model;
use MoonShine\Core\Exceptions\PageException;
use MoonShine\Laravel\Contracts\Fields\HasAsyncSearchContract;
use MoonShine\Laravel\Contracts\Fields\HasRelatedValuesContact;
use MoonShine\Laravel\Enums\Action;
use MoonShine\Laravel\Traits\Fields\BelongsToOrManyCreatable;
use MoonShine\Laravel\Traits\Fields\WithAsyncSearch;
use MoonShine\Laravel\Traits\Fields\WithRelatedValues;
use MoonShine\UI\Contracts\DefaultValueTypes\CanBeObject;
use MoonShine\UI\Contracts\HasDefaultValueContract;
use MoonShine\UI\Traits\Fields\HasPlaceholder;
use MoonShine\UI\Traits\Fields\Searchable;
use MoonShine\UI\Traits\Fields\WithDefaultValue;
use MoonShine\UI\Traits\Fields\WithEscapedValue;
use Throwable;

/**
 * @template-covariant R of \Illuminate\Database\Eloquent\Relations\BelongsTo
 *
 * @extends ModelRelationField<R>
 */
class BelongsTo extends ModelRelationField implements
    HasAsyncSearchContract,
    HasRelatedValuesContact,
    HasDefaultValueContract,
    CanBeObject
{
    use WithRelatedValues;
    use WithAsyncSearch;
    use Searchable;
    use WithDefaultValue;
    use HasPlaceholder;
    use BelongsToOrManyCreatable;
    use WithEscapedValue;

    protected string $view = 'moonshine::fields.relationships.belongs-to';

    protected bool $toOne = true;

    protected bool $native = false;

    /**
     * @throws Throwable
     */
    protected function resolvePreview(): string
    {
        if (! $this->getResource()->hasAnyAction(Action::VIEW, Action::UPDATE)) {
            return $this->isUnescape()
                ? parent::resolvePreview()
                : $this->escapeValue((string) parent::resolvePreview());
        }

        if (! $this->hasLink() && $this->toValue()) {
            $page = $this->getResource()->hasAction(Action::UPDATE)
                ? $this->getResource()->getFormPage()
                : $this->getResource()->getDetailPage();

            if (\is_null($page)) {
                throw PageException::required();
            }

            $this->link(
                $this->getResource()->getPageUrl($page, ['resourceItem' => $this->getValue()]),
                withoutIcon: true
            );
        }

        return $this->isUnescape()
            ? parent::resolvePreview()
            : $this->escapeValue((string) parent::resolvePreview());
    }

    protected function resolveValue(): mixed
    {
        if (\is_scalar($this->toValue())) {
            return $this->toValue();
        }

        return $this->toValue()?->getKey();
    }

    public function isSelected(string $value): bool
    {
        if (! $this->toValue()) {
            return false;
        }

        return (string) $this->toValue()->getKey() === $value;
    }

    public function native(): static
    {
        $this->native = true;

        return $this;
    }

    protected function isNative(): bool
    {
        return $this->native;
    }

    protected function resolveOnApply(): ?Closure
    {
        return function (Model $item) {
            $value = $this->getRequestValue();

            if ($value === false && ! $this->isNullable()) {
                return $item;
            }

            if ($value === false && $this->isNullable()) {
                return $item
                    ->{$this->getRelationName()}()
                    ->dissociate();
            }

            return $item->{$this->getRelationName()}()
                ->associate($value);
        };
    }

    public function prepareReactivityValue(mixed $value, mixed &$casted, array &$except): mixed
    {
        $value = data_get($value, 'value', $value);

        $casted = $this->getRelatedModel();
        $model = $this->makeRelatedModel($value, related: $this->getRelation()?->getRelated());
        $casted?->setRelation($this->getRelationName(), $model);

        /**
         * TODO(4.0) return $model
         */
        return $value;
    }

    /**
     * @throws Throwable
     */
    protected function viewData(): array
    {
        return [
            'isSearchable' => $this->isSearchable(),
            'values' => $this->getRelation() ? $this->getValues()->toArray() : [],
            'isNullable' => $this->isNullable(),
            'isAsyncSearch' => $this->isAsyncSearch(),
            'asyncSearchUrl' => $this->isAsyncSearch() ? $this->getAsyncSearchUrl() : '',
            'isCreatable' => $this->isCreatable(),
            'createButton' => $this->getCreateButton(),
            'fragmentUrl' => $this->getFragmentUrl(),
            'relationName' => $this->getRelationName(),
            'isNative' => $this->isNative(),
        ];
    }
}
